-- ============================================================
-- DEVELOPMENT USERS
-- ============================================================

INSERT INTO users (
    email,
    name,
    role
)
VALUES (
    'editor@example.com',
    'Demo Editor',
    'editor'
)
ON CONFLICT (email)
DO NOTHING;


INSERT INTO users (
    email,
    name,
    role
)
VALUES (
    'publisher@example.com',
    'Demo Publisher',
    'publisher'
)
ON CONFLICT (email)
DO NOTHING;