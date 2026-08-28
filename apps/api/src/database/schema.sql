create table if not exists users(id uuid primary key,email text unique not null,password_hash text not null,role text not null default 'user',created_at timestamptz default now());
create table if not exists subscriptions(id uuid primary key,user_id uuid not null,plan text not null,status text not null,created_at timestamptz default now());
create table if not exists signals(id uuid primary key,symbol text not null,exchange text not null,market text not null,direction text not null,confidence numeric not null,entry numeric,stop_loss numeric,targets jsonb,reasons jsonb,created_at timestamptz default now());
create table if not exists watchlists(id uuid primary key,user_id uuid not null,name text not null,created_at timestamptz default now());
create table if not exists audit_logs(id uuid primary key,user_id uuid,action text not null,metadata jsonb,created_at timestamptz default now());
