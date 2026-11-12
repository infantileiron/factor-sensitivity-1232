from uuid import uuid4
from fastapi import HTTPException
from ..models.review import FactorReview
from ..models.run import SensitivityRun
from ..services.run_service import ladder_status

def create(db,body):
 run=db.get(SensitivityRun,body.run_id)
 if run is None or run.status!="completed":raise HTTPException(409,"仅已完成运行可提交复核")
 progress=ladder_status(db,run)
 if progress and not progress.get('complete'):raise HTTPException(409,"Sobol档位未全部完成，暂不可复核")
 row=FactorReview(id=str(uuid4()),**body.model_dump(),state="submitted",reviewer="");db.add(row);db.commit();return row

def approve(db,row,user):
 if row.state!="submitted":raise HTTPException(409,"复核已处理")
 row.state="approved";row.reviewer=user.email;db.commit();return row
