"""Scrambled 2d Sobol A/B, centered Saltelli S1 and Jansen ST.

A study may ladder the base sample n=2^m from a small start power up to its
locked limit. Every stage uses the same scrambled sequence with the same seed,
so the stage designs are nested and reproducible. Each stage is estimated on
its own 2^m rows; adjacent stages are compared factor by factor.
"""
import numpy as np
from scipy.stats import qmc
from .polynomial import validate_model,validate_ranges,physical_points,evaluate,integer

def estimate(model,ranges,power=12,seed=20261112):
 """One Sobol/Saltelli stage at base sample n=2^power."""
 model=validate_model(model);ranges=validate_ranges(model,ranges);d=len(ranges)
 power=integer(power,'Sobol指数m',2,16);seed=integer(seed,'seed',0,2**32-1)
 unit=qmc.Sobol(d=2*d,scramble=True,seed=seed).random_base2(power);a,b=unit[:,:d],unit[:,d:]
 ya,yb=evaluate(model,physical_points(a,ranges)),evaluate(model,physical_points(b,ranges))
 combined=np.concatenate((ya,yb));mean=float(combined.mean());variance=float(np.mean((combined-mean)**2))
 if not np.isfinite(variance) or variance<=0:raise ValueError('代理响应方差为0或非有限，Sobol指数不可估')
 rows=[];warnings=[]
 for i,factor in enumerate(model['factors']):
  ab=a.copy();ab[:,i]=b[:,i];yab=evaluate(model,physical_points(ab,ranges))
  s1=float(np.mean((yb-mean)*(yab-ya))/variance);st=float(np.mean((ya-yab)**2)/(2*variance))
  if not np.isfinite([s1,st]).all():raise ValueError('Sobol指数非有限')
  rows.append({'factor_id':factor['factor_id'],'s1':s1,'st':st,'gap':st-s1})
  if s1<0 or s1>1 or st<0 or st>1:warnings.append(factor['factor_id']+'有限样本指数超出[0,1]，保留原值，不硬裁剪')
 if power<10:warnings.append('当前基础样本量较小，有限样本误差可能明显；点估计不作为置信区间')
 ranks={row['factor_id']:rank for rank,row in enumerate(sorted(rows,key=lambda row:(-row['st'],row['factor_id'])),start=1)}
 for row in rows:row['st_rank']=ranks[row['factor_id']]
 return {'indices':rows,'base_samples':2**power,'power':power,'dimension':2*d,'seed':seed,
  'evaluations':(d+2)*2**power,'response_mean':mean,'response_variance':variance,'variance_ddof':0,
  'method':'scrambled Sobol(2d); centered Saltelli S1 / Jansen ST','warnings':warnings,
  'note':'独立均匀因子范围；VarY为A/B合并总体方差。有限样本点估计，无置信区间或真实节能收益承诺。'}

def stages(model,ranges,start_power=9,power=12,seed=20261112):
 """Return stage records from start_power through power, each doubled."""
 model=validate_model(model);ranges=validate_ranges(model,ranges);d=len(ranges)
 start_power=integer(start_power,'Sobol起始m',2,16);power=integer(power,'Sobol指数m',2,16)
 seed=integer(seed,'seed',0,2**32-1)
 if start_power>power:raise ValueError('Sobol起始m不能大于上限m')
 result=[];previous={}
 for stage_power in range(start_power,power+1):
  stage=estimate(model,ranges,stage_power,seed)
  previous_power=result[-1]['power'] if result else None
  for row in stage['indices']:
   before=previous.get(row['factor_id'])
   row['prev_power']=previous_power if before else None
   row['delta_s1']=row['s1']-before['s1'] if before else None
   row['delta_st']=row['st']-before['st'] if before else None
   row['delta_gap']=row['gap']-before['gap'] if before else None
   row['prev_st_rank']=before['st_rank'] if before else None
   row['st_rank_change']=before['st_rank']-row['st_rank'] if before else None
  stage['previous_power']=previous_power
  stage['new_evaluations']=stage['evaluations'] if not result else stage['evaluations']-result[-1]['evaluations']
  stage['cumulative_evaluations']=sum(item['evaluations'] for item in result)+stage['evaluations']
  result.append(stage);previous={row['factor_id']:row for row in stage['indices']}
 final=result[-1]
 return {'stages':result,'start_power':start_power,'power':power,'dimension':2*d,'seed':seed,
  'final':final,'total_evaluations':final['cumulative_evaluations'],
  'evaluation_accounting':'每档独立评估(d+2)n；累计评估数为起始档到当前档各档评估数之和，恢复时不重复计已落库档位。',
  'method':'scrambled Sobol(2d) 同seed嵌套点列；centered Saltelli S1 / Jansen ST',
  'note':'各档共用同一扰乱2d序列并按2^m截取，基础n逐档加倍；相邻档差异为有限样本点估计差，不是置信区间。'}

def sobol(model,ranges,power=12,seed=20261112):
 """Single final-stage estimate kept for direct callers and hand checks."""
 return estimate(model,ranges,power,seed)
