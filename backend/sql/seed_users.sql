-- 插入示例用户（与 users 表结构一致）
-- 幂等：若 username 已存在则跳过；可安全重复执行
-- 默认密码均为 <用户名>123，登录后请尽快修改

INSERT INTO users (id, username, display_name, password_hash, role, department, disabled, created_at) VALUES
(
    '6839f2bc6cfc4d26b56a4da979001bf9',
    'frank',
    'Frank（研发）',
    '$2b$12$oQAPJYX0urL3ZlNvHFZdHeyYWNVPCL9uJnkM9vn3XmisecYhd8Cb.',
    'tech',
    'tech',
    FALSE,
    now()
),
(
    'edcccb2d95de481cb6972f3f55f8e960',
    'grace',
    'Grace（财务）',
    '$2b$12$7fCNiQjgX1is.h6mkoS1K.3PLXMU1ZqN4ivVhf1EQzIaMMkESPIm.',
    'finance',
    'finance',
    FALSE,
    now()
),
(
    '72ecf62a12b34d268dfcfb0ed13b5ae2',
    'heidi',
    'Heidi（人事）',
    '$2b$12$QoTPEhgtP/LvITGZ5fFNye8XFkTgKzTuu2BJGJsKhGfu54dAzopni',
    'hr',
    'hr',
    FALSE,
    now()
),
(
    '69337f421ced4eb6ab98069798f035b8',
    'ivan',
    'Ivan（销售）',
    '$2b$12$1OP4NT.p71YGSTG2MJEqT./7s6ebqlckuHKehMPN75UDm3JY6ljf6',
    'sales',
    'sales',
    FALSE,
    now()
),
(
    '8b1c79a219af486ebaf1e47917e060df',
    'judy',
    'Judy（普通员工）',
    '$2b$12$tpQS69zEOQIonBtuAIIxguWEHKsucBT8RlQ23kQ1hO14jjKBXvuAW',
    'employee',
    'general',
    FALSE,
    now()
)
ON CONFLICT (username) DO NOTHING;
