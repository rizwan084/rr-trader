create extension if not exists pgcrypto;
create table if not exists users(id uuid primary key default gen_random_uuid(),email text unique not null,password_hash text,role text not null default 'user',created_at timestamptz not null default now());
create table if not exists devices(id uuid primary key default gen_random_uuid(),user_id uuid not null references users(id) on delete cascade,device_key_hash text not null,last_seen_at timestamptz not null default now(),revoked_at timestamptz,created_at timestamptz not null default now(),unique(user_id,device_key_hash));
create table if not exists sessions(id uuid primary key default gen_random_uuid(),user_id uuid not null references users(id) on delete cascade,device_id uuid references devices(id) on delete cascade,token_hash text unique not null,expires_at timestamptz not null,revoked_at timestamptz,created_at timestamptz not null default now());
create table if not exists plans(id text primary key,name text not null,price numeric(12,2) not null default 0,currency text not null default 'USD',trial_days int not null default 0,active boolean not null default true,features jsonb not null default '{}'::jsonb);
insert into plans(id,name,price,trial_days,features) values('free','Free',0,3,'{"markets":2,"signals":false,"alerts":false}'),('pro','QuantEdge Pro',29.00,3,'{"markets":100,"signals":true,"alerts":true}') on conflict(id) do nothing;
create table if not exists subscriptions(id uuid primary key default gen_random_uuid(),user_id uuid not null references users(id) on delete cascade,plan_id text not null references plans(id),status text not null,trial_ends_at timestamptz,period_ends_at timestamptz,provider text,provider_customer_id text,provider_subscription_id text,created_at timestamptz not null default now(),updated_at timestamptz not null default now());
create table if not exists payments(id uuid primary key default gen_random_uuid(),user_id uuid references users(id),provider text not null,provider_event_id text unique,amount numeric(12,2),currency text,status text not null,metadata jsonb not null default '{}',created_at timestamptz not null default now());
create table if not exists watchlists(id uuid primary key default gen_random_uuid(),user_id uuid not null references users(id) on delete cascade,name text not null,created_at timestamptz not null default now());
create table if not exists signals(id uuid primary key default gen_random_uuid(),symbol text not null,exchange text not null,market text not null,direction text not null,setup_state text not null,confidence numeric not null,entry numeric,stop_loss numeric,targets jsonb not null default '[]',reasons jsonb not null default '[]',created_at timestamptz not null default now());
create table if not exists audit_logs(id uuid primary key default gen_random_uuid(),user_id uuid,action text not null,metadata jsonb,created_at timestamptz not null default now());
create index if not exists sessions_user_idx on sessions(user_id);create index if not exists subscriptions_user_idx on subscriptions(user_id);create index if not exists signals_created_idx on signals(created_at desc);
create table if not exists crypto_invoices(
 id uuid primary key default gen_random_uuid(),
 user_id uuid references users(id) on delete set null,
 email text,
 plan_id text not null references plans(id),
 network text not null default 'BEP20',
 chain_id int not null default 56,
 asset text not null default 'USDT',
 token_contract text not null,
 receive_address text not null,
 amount numeric(36,18) not null,
 status text not null default 'pending',
 tx_hash text unique,
 sender_address text,
 block_number bigint,
 confirmations int,
 paid_at timestamptz,
 expires_at timestamptz not null,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index if not exists crypto_invoices_status_idx on crypto_invoices(status,created_at desc);
