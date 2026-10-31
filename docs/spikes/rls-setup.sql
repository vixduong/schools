\set ON_ERROR_STOP on
-- owner (migrations) creates schema; app role cannot bypass RLS
CREATE ROLE app LOGIN PASSWORD 'app' NOBYPASSRLS;
CREATE TABLE school (id int PRIMARY KEY, name text);
CREATE TABLE score (id serial PRIMARY KEY, school_id int NOT NULL REFERENCES school, student text, value numeric(3,1));
ALTER TABLE score ENABLE ROW LEVEL SECURITY;
ALTER TABLE score FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant ON score
  USING (school_id = NULLIF(current_setting('app.school_id', true), '')::int)
  WITH CHECK (school_id = NULLIF(current_setting('app.school_id', true), '')::int);
GRANT SELECT, INSERT, UPDATE, DELETE ON score TO app; GRANT USAGE ON SEQUENCE score_id_seq TO app;
INSERT INTO school VALUES (1,'A'),(2,'B');
INSERT INTO score (school_id, student, value) VALUES (1,'An',8),(1,'Ha',9),(2,'Bao',6);
