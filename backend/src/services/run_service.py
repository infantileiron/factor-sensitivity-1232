"""Run orchestration: Morris followed by the Sobol stage ladder.

The study's Sobol ladder runs base samples n=2^m from sobol_start_power up to
the locked power limit. Each completed stage is committed on its own. A failure
marks the run failed with the last completed stage recorded; resuming continues
at the first missing stage without recomputing or rewriting persisted stages.
Duplicate queue delivery for an already claimed or completed run is a no-op.
"""
import json,hashlib
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import update,select,delete
from ..models.run import SensitivityRun
from ..models.study import SensitivityStudy
from ..models.response_model import ResponseModel
from ..models.space import FactorSpace
from ..models.factor_metric import FactorMetric
from ..models.elementary_effect import ElementaryEffect
from ..models.evaluation import EvaluationPoint
from ..models.sobol_stage import SobolStage,SobolStageIndex
from ..utils.queue import enqueue
from .model_service import specification
from .space_service import ranges
from .polynomial import validate_ranges
from .morris import morris
from .sobol import estimate as sobol_estimate

def powers(study):
 limit=study.power
 start=study.sobol_start_power if study.sobol_start_power is not None else limit
 return list(range(start,limit+1))

def create(db,body):
 if not db.get(SensitivityStudy,body.study_id):raise HTTPException(422,'敏感度研究不存在')
 row=SensitivityRun(id=str(uuid4()),study_id=body.study_id,status='queued',result={},error='',sobol_progress={});db.add(row);db.commit()
 try:enqueue(row.id)
 except Exception:
  row.status='failed';row.error='Redis队列不可用，请重试';db.commit();raise HTTPException(503,row.error)
 return row

def resume(db,ident):
 row=db.get(SensitivityRun,ident)
 if not row:raise HTTPException(404,'记录不存在')
 if row.status!='failed':raise HTTPException(409,'仅失败运行可从最近完成档恢复')
 row.status='queued';row.error='';db.commit()
 try:enqueue(row.id)
 except Exception:
  row.status='failed';row.error='Redis队列不可用，请重试';db.commit();raise HTTPException(503,row.error)
 return row

def _stage_rows(db,run_id):
 rows=db.scalars(select(SobolStage).where(SobolStage.run_id==run_id).order_by(SobolStage.power)).all()
 stage_ids=[row.id for row in rows]
 index_rows=db.scalars(select(SobolStageIndex).where(SobolStageIndex.stage_id.in_(stage_ids)).order_by(SobolStageIndex.st_rank)).all() if stage_ids else []
 by_stage={}
 for item in index_rows:by_stage.setdefault(item.stage_id,[]).append(item)
 result=[]
 for row in rows:
  indices=[{'factor_id':item.factor_id,'s1':item.s1,'st':item.st,'gap':item.gap,'st_rank':item.st_rank,
   'prev_st_rank':item.prev_st_rank,'st_rank_change':item.st_rank_change,
   'prev_power':item.prev_power,'delta_s1':item.delta_s1,'delta_st':item.delta_st,'delta_gap':item.delta_gap} for item in by_stage.get(row.id,[])]
  result.append({'power':row.power,'base_samples':row.base_samples,'evaluations':row.evaluations,
   'cumulative_evaluations':row.cumulative_evaluations,'response_mean':row.response_mean,
   'response_variance':row.response_variance,'variance_ddof':0,'seed':row.seed,'warnings':row.warnings,'indices':indices})
 return result

def _progress(start,limit,stage_rows,failed_power=None):
 expected=list(range(start,limit+1));completed=[row['power'] for row in stage_rows]
 missing=[power for power in expected if power not in completed]
 return {'ladder':start<limit,'start_power':start,'limit_power':limit,'expected_powers':expected,
  'completed_powers':completed,'completed_stages':len(completed),'expected_stages':len(expected),
  'last_completed_power':completed[-1] if completed else None,
  'resume_from_power':missing[0] if missing else None,'failed_power':failed_power,
  'complete':not missing,'cumulative_evaluations':stage_rows[-1]['cumulative_evaluations'] if stage_rows else 0}

def _persist_stage(db,run,power,stage,previous,cumulative_prior):
 evaluations=stage['evaluations'];cumulative=cumulative_prior+evaluations
 stage_row=SobolStage(id=str(uuid4()),run_id=run.id,power=power,base_samples=stage['base_samples'],
  evaluations=evaluations,cumulative_evaluations=cumulative,response_mean=stage['response_mean'],
  response_variance=stage['response_variance'],seed=stage['seed'],warnings=stage['warnings'])
 db.add(stage_row)
 for index in stage['indices']:
  before=previous.get(index['factor_id'])
  db.add(SobolStageIndex(id=str(uuid4()),stage_id=stage_row.id,factor_id=index['factor_id'],s1=index['s1'],
   st=index['st'],gap=index['gap'],st_rank=index['st_rank'],
   prev_st_rank=before['st_rank'] if before else None,
   st_rank_change=before['st_rank']-index['st_rank'] if before else None,
   prev_power=before['power'] if before else None,
   delta_s1=index['s1']-before['s1'] if before else None,delta_st=index['st']-before['st'] if before else None,
   delta_gap=index['gap']-before['gap'] if before else None))
 return stage_row

def ladder_status(db,row):
 """Current ladder view for a run; legacy single-stage runs report complete."""
 study=db.get(SensitivityStudy,row.study_id)
 if not study:return None
 stage_rows=_stage_rows(db,row.id)
 if not stage_rows:return None
 start=(study.sobol_start_power if study.sobol_start_power is not None else study.power)
 progress=_progress(start,study.power,stage_rows)
 return progress

def compute(db,ident):
 # Atomic claim: duplicate delivery for a claimed/running/completed run does nothing.
 claim=db.execute(update(SensitivityRun).where(SensitivityRun.id==ident,SensitivityRun.status=='queued').values(status='running'))
 db.commit()
 if claim.rowcount!=1:return
 row=db.get(SensitivityRun,ident)
 start=limit=None
 try:
  study=db.get(SensitivityStudy,row.study_id);modelrow=db.get(ResponseModel,study.model_id);spacerow=db.get(FactorSpace,study.space_id)
  model=specification(db,modelrow);bounds=validate_ranges(model,ranges(db,spacerow))
  stage_list=powers(study);start,limit=stage_list[0],stage_list[-1];d=len(bounds)
  config={k:getattr(study,k) for k in ['trajectories','levels','power','seed','sobol_start_power']}
  fingerprint=hashlib.sha256(json.dumps({'model':model,'ranges':bounds,'config':config},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  prior=row.result or {}
  if prior.get('input_sha256')==fingerprint and prior.get('morris'):
   # Resume: keep the already recorded Morris record instead of recomputing it.
   local=prior['morris']
  else:
   local=morris(model,bounds,study.trajectories,study.levels,study.seed)
   prior={}
  persisted={item['power']:item for item in _stage_rows(db,row.id)}
  if prior.get('input_sha256')!=fingerprint:
   row.result={'model_name':modelrow.name,'space_name':spacerow.name,'study_name':study.name,'model':model,
    'ranges':bounds,'config':config,'morris':local,'input_sha256':fingerprint,
    'assumptions':'受控多项式模拟代理；因子独立均匀分布。Morris EE按归一空间步长；Sobol分档共享同一seed点列，指数为有限样本点估计，无CI，不代表真实节能收益。',
    'sobol_stages':list(persisted.values())}
   db.commit();prior=row.result
  expected=sorted(persisted)
  if expected and expected!=list(range(start,expected[-1]+1)):
   raise ValueError('Sobol分档不连续，无法从最近完成档恢复')
  previous={index['factor_id']:{'power':expected[-1],**index} for index in persisted[expected[-1]]['indices']} if expected else {}
  cumulative=persisted[expected[-1]]['cumulative_evaluations'] if expected else 0
  for power in stage_list:
   if power in persisted:
    previous={index['factor_id']:{'power':power,**index} for index in persisted[power]['indices']}
    cumulative=persisted[power]['cumulative_evaluations']
    continue
   if power-1 not in persisted and power>start:
    raise ValueError('Sobol分档不连续，无法从最近完成档恢复')
   stage=sobol_estimate(model,bounds,power,study.seed)
   stage['new_evaluations']=(d+2)*2**power
   stage['cumulative_evaluations']=cumulative+stage['evaluations']
   _persist_stage(db,row,power,stage,previous,cumulative)
   cumulative=stage['cumulative_evaluations']
   persisted[power]={**stage,'power':power}
   previous={index['factor_id']:{'power':power,**index} for index in stage['indices']}
   stage_rows=_stage_rows(db,row.id);progress=_progress(start,limit,stage_rows)
   row.result={**row.result,'sobol_stages':stage_rows,'sobol_progress':progress}
   row.sobol_progress=progress
   db.commit()
  stage_rows=_stage_rows(db,row.id);progress=_progress(start,limit,stage_rows)
  final=stage_rows[-1]
  global_={'indices':final['indices'],'base_samples':final['base_samples'],'power':final['power'],
   'dimension':2*d,'seed':final['seed'],'evaluations':final['evaluations'],
   'response_mean':final['response_mean'],'response_variance':final['response_variance'],'variance_ddof':0,
   'method':'scrambled Sobol(2d) 同seed嵌套点列；centered Saltelli S1 / Jansen ST','warnings':final['warnings'],
   'note':'各档共用同一扰乱2d序列并按2^m截取，基础n逐档加倍；相邻档差异为有限样本点估计差，不是置信区间。'}
  local_indices={item['factor_id']:item for item in local['indices']}
  final_indices={item['factor_id']:item for item in final['indices']}
  metrics=[{**f,**bounds[i],**local_indices[f['factor_id']],**final_indices[f['factor_id']]} for i,f in enumerate(model['factors'])]
  for child in (FactorMetric,ElementaryEffect,EvaluationPoint):db.execute(delete(child).where(child.run_id==row.id))
  for metric in metrics:db.add(FactorMetric(id=str(uuid4()),run_id=row.id,**{k:metric[k] for k in ['factor_id','mu','mu_star','sigma','s1','st','gap','effect_count','sigma_denominator']}))
  for trajectory in local['trajectories']:
   for step,effect in enumerate(trajectory['steps']):db.add(ElementaryEffect(id=str(uuid4()),run_id=row.id,trajectory=trajectory['trajectory'],**effect))
   for step,response in enumerate(trajectory['responses']):db.add(EvaluationPoint(id=str(uuid4()),run_id=row.id,trajectory=trajectory['trajectory'],step=step,normalized=trajectory['normalized'][step],physical=trajectory['physical'][step],response=response))
  row.result={**row.result,'sobol':global_,'sobol_stages':stage_rows,'sobol_progress':progress,'metrics':metrics,
   'warnings':final['warnings'],'total_evaluations':local['evaluations']+progress['cumulative_evaluations']}
  row.sobol_progress=progress
  row.response_mean=final['response_mean'];row.response_variance=final['response_variance']
  row.status='completed';row.error='';db.commit()
 except Exception as error:
  db.rollback();row=db.get(SensitivityRun,ident)
  if row is None or row.status!='running':return
  stage_rows=_stage_rows(db,row.id);progress=dict(row.sobol_progress or {})
  study=db.get(SensitivityStudy,row.study_id)
  if start is None and study:
   start=study.sobol_start_power if study.sobol_start_power is not None else study.power
  if limit is None and study:limit=study.power
  if start is None:start=progress.get('start_power',stage_rows[0]['power'] if stage_rows else 0)
  if limit is None:limit=progress.get('limit_power',stage_rows[-1]['power'] if stage_rows else start)
  failed=_progress(start,limit,stage_rows)
  failed['failed_power']=failed.get('resume_from_power')
  row.result={**(row.result or {}),'sobol_progress':failed}
  row.sobol_progress=failed;row.status='failed';row.error=str(error)[:1000];db.commit()
