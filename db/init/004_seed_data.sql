TRUNCATE TABLE business_data.employees RESTART IDENTITY;
TRUNCATE TABLE business_data.students RESTART IDENTITY;

INSERT INTO business_data.employees (
    full_name,
    status,
    salary,
    department,
    hired_at
)
SELECT
    'Employee ' || gs,
    CASE
        WHEN gs <= 35 THEN 'active'
        WHEN gs <= 135 THEN 'inactive'
        WHEN gs % 10 = 0 THEN 'inactive'
        ELSE 'active'
    END,
    CASE
        WHEN gs <= 10 THEN -1000
        WHEN gs <= 35 THEN NULL
        WHEN gs <= 135 THEN -500
        ELSE 50000 + (gs % 10000)
    END,
    CASE
        WHEN gs % 4 = 0 THEN 'Engineering'
        WHEN gs % 4 = 1 THEN 'Sales'
        WHEN gs % 4 = 2 THEN 'Finance'
        ELSE 'Operations'
    END,
    DATE '2020-01-01' + ((gs % 1500) * INTERVAL '1 day')
FROM generate_series(1, 100000) AS gs;

INSERT INTO business_data.students (
    full_name,
    enrollment_date,
    admission_status,
    grade_level
)
SELECT
    'Student 2026 Enrolled ' || gs,
    DATE '2026-01-01' + ((gs % 365) * INTERVAL '1 day'),
    'enrolled',
    'Year ' || ((gs % 4) + 1)
FROM generate_series(1, 1200) AS gs;

INSERT INTO business_data.students (
    full_name,
    enrollment_date,
    admission_status,
    grade_level
)
SELECT
    'Student 2025 Enrolled ' || gs,
    DATE '2025-01-01' + ((gs % 365) * INTERVAL '1 day'),
    'enrolled',
    'Year ' || ((gs % 4) + 1)
FROM generate_series(1, 850) AS gs;

INSERT INTO business_data.students (
    full_name,
    enrollment_date,
    admission_status,
    grade_level
)
SELECT
    'Student 2026 Cancelled ' || gs,
    DATE '2026-01-01' + ((gs % 365) * INTERVAL '1 day'),
    'cancelled',
    'Year ' || ((gs % 4) + 1)
FROM generate_series(1, 100) AS gs;

INSERT INTO business_data.students (
    full_name,
    enrollment_date,
    admission_status,
    grade_level
)
SELECT
    'Student Additional ' || gs,
    DATE '2024-01-01' + ((gs % 1095) * INTERVAL '1 day'),
    CASE
        WHEN gs % 9 = 0 THEN 'rejected'
        WHEN gs % 13 = 0 THEN 'cancelled'
        ELSE 'applied'
    END,
    'Year ' || ((gs % 4) + 1)
FROM generate_series(1, 7850) AS gs;
