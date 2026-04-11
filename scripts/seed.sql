-- Seed: default roles
INSERT INTO roles (id, code, name) VALUES
    (uuid_generate_v4(), 'guest',    'Guest'),
    (uuid_generate_v4(), 'business', 'Business'),
    (uuid_generate_v4(), 'expert',   'Expert')
ON CONFLICT (code) DO NOTHING;
