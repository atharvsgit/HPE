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
    first_names[((gs * 7) % array_length(first_names, 1)) + 1]
        || ' '
        || last_names[((gs * 11) % array_length(last_names, 1)) + 1],
    CASE
        WHEN gs <= 30 THEN 'active'
        WHEN gs % 997 = 0 THEN 'inactive'
        WHEN gs % 37 = 0 THEN 'leave'
        WHEN gs % 11 = 0 THEN 'inactive'
        ELSE 'active'
    END,
    CASE
        WHEN gs <= 10 THEN -1 * (750 + (gs * 137))
        WHEN gs BETWEEN 11 AND 30 THEN NULL
        WHEN gs % 997 = 0 THEN -1 * (300 + (gs % 700))
        ELSE ROUND((42000 + ((gs * 7919) % 148000) + ((gs % 100) * 0.37))::NUMERIC, 2)
    END,
    departments[((gs * 5) % array_length(departments, 1)) + 1],
    DATE '2016-01-01' + (((gs * 17) % 3400)::int)
FROM
    generate_series(1, 100000) AS gs
    CROSS JOIN (
        SELECT
            ARRAY[
                'Aarav', 'Aisha', 'Amelia', 'Arjun', 'Avery', 'Carlos', 'Diya', 'Elena',
                'Ethan', 'Fatima', 'Grace', 'Hannah', 'Ibrahim', 'Isha', 'Jacob', 'Jia',
                'Kabir', 'Leah', 'Liam', 'Maya', 'Mia', 'Noah', 'Nora', 'Olivia',
                'Priya', 'Rahul', 'Riya', 'Samir', 'Sara', 'Sofia', 'Theo', 'Vivaan',
                'Zara'
            ] AS first_names,
            ARRAY[
                'Anderson', 'Bansal', 'Brown', 'Chen', 'Davis', 'Fernandez', 'Garcia',
                'Gupta', 'Iyer', 'Johnson', 'Kapoor', 'Khan', 'Kim', 'Lee', 'Mehta',
                'Miller', 'Nair', 'Patel', 'Rao', 'Roy', 'Shah', 'Singh', 'Smith',
                'Thomas', 'Verma', 'Williams'
            ] AS last_names,
            ARRAY[
                'Engineering', 'Sales', 'Finance', 'Operations', 'People Ops',
                'Legal', 'Product', 'Customer Success', 'Security', 'Marketing',
                'Data Platform', 'Procurement'
            ] AS departments
    ) AS seed_values;

INSERT INTO business_data.students (
    full_name,
    enrollment_date,
    admission_status,
    grade_level
)
SELECT
    first_names[((gs * 13) % array_length(first_names, 1)) + 1]
        || ' '
        || last_names[((gs * 17) % array_length(last_names, 1)) + 1],
    DATE '2023-08-01' + (((gs * 19) % 980)::int),
    CASE
        WHEN gs % 41 = 0 THEN 'waitlisted'
        WHEN gs % 17 = 0 THEN 'cancelled'
        WHEN gs % 13 = 0 THEN 'rejected'
        WHEN gs % 7 = 0 THEN 'applied'
        ELSE 'enrolled'
    END,
    grade_levels[((gs * 3) % array_length(grade_levels, 1)) + 1]
FROM
    generate_series(1, 10000) AS gs
    CROSS JOIN (
        SELECT
            ARRAY[
                'Aditya', 'Ananya', 'Ava', 'Benjamin', 'Camila', 'Daniel', 'Emma',
                'Farhan', 'Harper', 'Ishaan', 'Kiara', 'Lucas', 'Meera', 'Nina',
                'Omar', 'Reyansh', 'Saanvi', 'Tara', 'Vihaan', 'Yusuf', 'Zoe'
            ] AS first_names,
            ARRAY[
                'Agarwal', 'Ali', 'Bose', 'Chatterjee', 'Das', 'Evans', 'Ghosh',
                'Hernandez', 'Joshi', 'Kumar', 'Malhotra', 'Martin', 'Menon',
                'Murphy', 'Nguyen', 'Pillai', 'Reddy', 'Saxena', 'Sharma',
                'Walker'
            ] AS last_names,
            ARRAY['Freshman', 'Sophomore', 'Junior', 'Senior'] AS grade_levels
    ) AS seed_values;
