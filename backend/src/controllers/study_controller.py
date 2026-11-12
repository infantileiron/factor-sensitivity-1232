from sqlalchemy import select
from ..models.study import SensitivityStudy
from ..models.common import serialize
from ..services import study_service as service
from ..services.run_service import powers
from .common import require
def expanded(row):return {**serialize(row),'sobol_stage_powers':powers(row)}
def list_all(db):return [expanded(row) for row in db.scalars(select(SensitivityStudy).order_by(SensitivityStudy.created_at.desc())).all()]
def detail(db,ident):
 row=require(db,SensitivityStudy,ident)
 return expanded(row)
def create(db,body):
 row=service.create(db,body)
 return expanded(row)
