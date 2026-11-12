from sqlalchemy import String,Text,JSON,ForeignKey,Double,BigInteger,Integer,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class SobolStage(RecordMixin,Base):
 __tablename__="sobol_stages"
 __table_args__=(UniqueConstraint("run_id","power",name="uq_sobol_stage_run_power"),)
 run_id:Mapped[str]=mapped_column(ForeignKey("runs.id"))
 power:Mapped[int]=mapped_column(Integer)
 base_samples:Mapped[int]=mapped_column(BigInteger)
 evaluations:Mapped[int]=mapped_column(Integer)
 cumulative_evaluations:Mapped[int]=mapped_column(BigInteger)
 response_mean:Mapped[float]=mapped_column(Double)
 response_variance:Mapped[float]=mapped_column(Double)
 seed:Mapped[int]=mapped_column(BigInteger)
 warnings:Mapped[list]=mapped_column(JSON,default=list)
class SobolStageIndex(RecordMixin,Base):
 __tablename__="sobol_stage_indices"
 stage_id:Mapped[str]=mapped_column(ForeignKey("sobol_stages.id"))
 factor_id:Mapped[str]=mapped_column(String(32))
 s1:Mapped[float]=mapped_column(Double)
 st:Mapped[float]=mapped_column(Double)
 gap:Mapped[float]=mapped_column(Double)
 st_rank:Mapped[int]=mapped_column(Integer)
 prev_st_rank:Mapped[int|None]=mapped_column(Integer,nullable=True)
 st_rank_change:Mapped[int|None]=mapped_column(Integer,nullable=True)
 prev_power:Mapped[int|None]=mapped_column(Integer,nullable=True)
 delta_s1:Mapped[float|None]=mapped_column(Double,nullable=True)
 delta_st:Mapped[float|None]=mapped_column(Double,nullable=True)
 delta_gap:Mapped[float|None]=mapped_column(Double,nullable=True)
