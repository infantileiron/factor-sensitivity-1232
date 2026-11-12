-- Incremental migration for existing databases (new databases are created from SQLAlchemy metadata).
-- Adds the Sobol stage ladder without touching old runs or approved reports.
-- Old runs keep their stored result JSON and report snapshots; they simply have no stage rows.

ALTER TABLE studies ADD COLUMN sobol_start_power INT NULL AFTER seed;
ALTER TABLE runs ADD COLUMN sobol_progress JSON NULL AFTER response_variance;

CREATE TABLE IF NOT EXISTS sobol_stages (
 id VARCHAR(36) NOT NULL,
 created_at DATETIME NOT NULL,
 run_id VARCHAR(36) NOT NULL,
 power INT NOT NULL,
 base_samples BIGINT NOT NULL,
 evaluations INT NOT NULL,
 cumulative_evaluations BIGINT NOT NULL,
 response_mean DOUBLE NOT NULL,
 response_variance DOUBLE NOT NULL,
 seed BIGINT NOT NULL,
 warnings JSON NOT NULL,
 PRIMARY KEY (id),
 UNIQUE KEY uq_sobol_stage_run_power (run_id,power),
 CONSTRAINT fk_sobol_stages_run FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS sobol_stage_indices (
 id VARCHAR(36) NOT NULL,
 created_at DATETIME NOT NULL,
 stage_id VARCHAR(36) NOT NULL,
 factor_id VARCHAR(32) NOT NULL,
 s1 DOUBLE NOT NULL,
 st DOUBLE NOT NULL,
 gap DOUBLE NOT NULL,
 st_rank INT NOT NULL,
 prev_st_rank INT NULL,
 st_rank_change INT NULL,
 prev_power INT NULL,
 delta_s1 DOUBLE NULL,
 delta_st DOUBLE NULL,
 delta_gap DOUBLE NULL,
 PRIMARY KEY (id),
 CONSTRAINT fk_sobol_stage_indices_stage FOREIGN KEY (stage_id) REFERENCES sobol_stages(id)
);
