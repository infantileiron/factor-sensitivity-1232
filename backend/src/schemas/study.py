from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,FiniteFloat,model_validator
class StudyCreate(BaseModel):
 model_config=ConfigDict(extra='forbid')
 name:str=Field(min_length=2,max_length=180)
 model_id:str
 space_id:str
 trajectories:int=Field(default=24,ge=2,le=128)
 levels:int=Field(default=6,ge=2,le=20)
 power:int=Field(default=12,ge=2,le=16)
 sobol_start_power:int|None=Field(default=None,ge=2,le=16)
 seed:int=Field(default=20261112,ge=0,le=4294967295)
 @model_validator(mode='after')
 def even_grid(self):
  if self.levels%2:raise ValueError('Morris网格级数p必须为偶数')
  return self
 @model_validator(mode='after')
 def ladder_order(self):
  if self.sobol_start_power is not None and self.sobol_start_power>self.power:raise ValueError('Sobol起始m不能大于上限m')
  return self
