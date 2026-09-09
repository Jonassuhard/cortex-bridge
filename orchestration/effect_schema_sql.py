"""Exact v3 DDL from the approved durable-effects implementation plan."""

V3_DDL = """
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at REAL NOT NULL
);
CREATE TABLE control_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  state TEXT NOT NULL CHECK (state IN ('inactive','stopping','stopped','resetting')),
  stop_requested_at REAL,
  stopped_at REAL,
  reset_at REAL,
  updated_at REAL NOT NULL
);
CREATE TABLE approvals (
  id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('mission','local_alias_action')),
  mission_id TEXT REFERENCES missions(id),
  local_action_id TEXT REFERENCES local_alias_actions(action_id),
  action_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  arguments_digest TEXT NOT NULL CHECK (length(arguments_digest) = 64),
  nonce TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL CHECK (scope IN ('once','tool-for-mission','all-writes-for-mission')),
  decision TEXT NOT NULL CHECK (decision IN ('pending','approved','denied','invalidated')),
  nonce_consumed_at REAL,
  effect_consumed_at REAL,
  created_at REAL NOT NULL,
  decided_at REAL,
  CHECK ((owner_kind='mission' AND mission_id IS NOT NULL AND local_action_id IS NULL) OR
         (owner_kind='local_alias_action' AND mission_id IS NULL AND
          local_action_id IS NOT NULL AND action_id=local_action_id AND scope='once'))
);
CREATE UNIQUE INDEX approvals_mission_exact
ON approvals(mission_id, action_id, epoch, arguments_digest)
WHERE owner_kind='mission';
CREATE UNIQUE INDEX approvals_local_alias_one_per_action
ON approvals(local_action_id)
WHERE owner_kind='local_alias_action';
CREATE TABLE effects (
  id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('mission','direct_ui','admin_ui','local_alias_action')),
  mission_id TEXT REFERENCES missions(id),
  action_id TEXT,
  request_id TEXT,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  operation TEXT NOT NULL,
  payload_digest TEXT NOT NULL CHECK (length(payload_digest) = 64),
  parent_effect_id TEXT REFERENCES effects(id),
  category TEXT NOT NULL CHECK (category IN ('filesystem','process','browser','sensitive_read')),
  state TEXT NOT NULL CHECK (state IN ('intent','active','succeeded','failed','outcome_unclear')),
  authorization_json TEXT NOT NULL,
  intent_json TEXT NOT NULL,
  ownership_json TEXT,
  receipt_json TEXT,
  error_code TEXT,
  created_at REAL NOT NULL,
  activated_at REAL,
  finished_at REAL,
  CHECK ((owner_kind='mission' AND mission_id IS NOT NULL AND request_id IS NULL) OR
         (owner_kind IN ('direct_ui','admin_ui') AND mission_id IS NULL AND
          action_id IS NULL AND request_id IS NOT NULL) OR
         (owner_kind='local_alias_action' AND mission_id IS NULL AND
          action_id IS NOT NULL AND request_id IS NULL))
);
CREATE UNIQUE INDEX effects_direct_request
ON effects(request_id)
WHERE owner_kind IN ('direct_ui','admin_ui');
CREATE UNIQUE INDEX effects_local_alias_action
ON effects(action_id)
WHERE owner_kind='local_alias_action';

CREATE TABLE local_alias_catalog (
  catalog_entry_id TEXT PRIMARY KEY,
  revision INTEGER NOT NULL,
  alias TEXT NOT NULL UNIQUE CHECK (alias IN ('desktop','documents','downloads')),
  label TEXT NOT NULL,
  provenance TEXT NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE local_alias_access_observations (
  observation_id TEXT PRIMARY KEY,
  effect_id TEXT NOT NULL UNIQUE,
  catalog_entry_id TEXT NOT NULL,
  catalog_revision INTEGER NOT NULL,
  alias TEXT NOT NULL CHECK (alias IN ('desktop','documents','downloads')),
  authorization_epoch INTEGER NOT NULL,
  device INTEGER NOT NULL,
  inode INTEGER NOT NULL,
  uid INTEGER NOT NULL,
  mode INTEGER NOT NULL,
  verified_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  FOREIGN KEY (catalog_entry_id) REFERENCES local_alias_catalog(catalog_entry_id)
);
CREATE TABLE local_alias_grants (
  grant_id TEXT PRIMARY KEY,
  action_id TEXT NOT NULL UNIQUE,
  catalog_entry_id TEXT NOT NULL,
  catalog_revision INTEGER NOT NULL,
  access_observation_id TEXT NOT NULL,
  alias TEXT NOT NULL CHECK (alias IN ('desktop','documents','downloads')),
  operation TEXT NOT NULL CHECK (operation = 'create_directory'),
  allowed_leaf TEXT NOT NULL,
  route_digest TEXT NOT NULL,
  stop_epoch INTEGER NOT NULL,
  authorization_epoch INTEGER NOT NULL,
  device INTEGER NOT NULL,
  inode INTEGER NOT NULL,
  uid INTEGER NOT NULL,
  mode INTEGER NOT NULL,
  FOREIGN KEY (catalog_entry_id) REFERENCES local_alias_catalog(catalog_entry_id),
  FOREIGN KEY (access_observation_id) REFERENCES local_alias_access_observations(observation_id)
);
CREATE TABLE local_alias_actions (
  action_id TEXT PRIMARY KEY,
  grant_id TEXT NOT NULL UNIQUE,
  idempotency_key TEXT NOT NULL UNIQUE,
  payload_digest TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN (
    'awaiting_approval','active','created','failed_safe',
    'outcome_unclear','cancelled_by_stop'
  )),
  created_inode INTEGER,
  terminal_code TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  FOREIGN KEY (grant_id) REFERENCES local_alias_grants(grant_id)
);
"""
