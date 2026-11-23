BEGIN;
CREATE TABLE IF NOT EXISTS public.career_account (
  namespace TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  email TEXT NOT NULL CHECK (email = lower(email)),
  name VARCHAR(60) NOT NULL,
  password_hash TEXT NOT NULL,
  age SMALLINT CHECK (age BETWEEN 0 AND 120),
  school VARCHAR(60) NOT NULL DEFAULT '',
  major VARCHAR(60) NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(namespace, subject_id),
  UNIQUE(namespace, email)
);
CREATE TABLE IF NOT EXISTS public.career_account_oauth (
  namespace TEXT NOT NULL,
  provider TEXT NOT NULL CHECK (provider = 'kakao'),
  provider_subject TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(namespace, provider, provider_subject),
  UNIQUE(namespace, provider, subject_id),
  FOREIGN KEY(namespace, subject_id) REFERENCES public.career_account ON DELETE CASCADE
);
COMMENT ON TABLE public.career_account IS
  'Career member identities and optional registration details. Passwords are salted scrypt hashes. Namespace isolates local and staging accounts.';
COMMIT;
