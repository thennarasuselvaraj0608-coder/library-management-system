-- ============================================================================
-- Automated Library Book Tracking and Management System
-- Database Schema: library_management_db
-- Target: MySQL 8.0+ / MySQL Workbench
-- Department: Artificial Intelligence and Data Science (AI & DS)
-- ============================================================================

-- 1. Create and Select Database
CREATE DATABASE IF NOT EXISTS library_management_db;
USE library_management_db;

-- ============================================================================
-- 2. Table Definitions with Primary Keys, Foreign Keys, & Constraints
-- ============================================================================

-- Table 1: departments
-- Represents academic departments (AIDS, CSE, IT, ECE, MECH, etc.)
CREATE TABLE IF NOT EXISTS departments (
    department_id INT AUTO_INCREMENT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table 2: authors
-- Represents book authors (Normalized to eliminate redundancy)
CREATE TABLE IF NOT EXISTS authors (
    author_id INT AUTO_INCREMENT PRIMARY KEY,
    author_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table 3: categories
-- Represents genre/domain classification for books
CREATE TABLE IF NOT EXISTS categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table 4: librarians
-- Represents library staff managing issue/return operations
CREATE TABLE IF NOT EXISTS librarians (
    librarian_id INT AUTO_INCREMENT PRIMARY KEY,
    librarian_name VARCHAR(100) NOT NULL,
    phone VARCHAR(15) DEFAULT NULL,
    email VARCHAR(100) DEFAULT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table 5: students
-- Represents registered college students who can borrow books
CREATE TABLE IF NOT EXISTS students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    register_number VARCHAR(20) NOT NULL UNIQUE,
    student_name VARCHAR(100) NOT NULL,
    department_id INT DEFAULT NULL,
    year_of_study INT DEFAULT 1,
    phone VARCHAR(15) DEFAULT NULL,
    email VARCHAR(100) DEFAULT NULL UNIQUE,
    CONSTRAINT fk_students_department 
        FOREIGN KEY (department_id) REFERENCES departments(department_id) 
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT chk_student_year 
        CHECK (year_of_study BETWEEN 1 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table 6: books
-- Tracks book inventory, ISBN, total copies, and available copies
CREATE TABLE IF NOT EXISTS books (
    book_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    isbn VARCHAR(20) DEFAULT NULL UNIQUE,
    author_id INT DEFAULT NULL,
    category_id INT DEFAULT NULL,
    publisher VARCHAR(100) DEFAULT NULL,
    total_copies INT NOT NULL DEFAULT 1,
    available_copies INT NOT NULL DEFAULT 1,
    CONSTRAINT fk_books_author 
        FOREIGN KEY (author_id) REFERENCES authors(author_id) 
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_books_category 
        FOREIGN KEY (category_id) REFERENCES categories(category_id) 
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT books_chk_total_copies 
        CHECK (total_copies >= 0),
    CONSTRAINT books_chk_available_copies 
        CHECK (available_copies >= 0),
    CONSTRAINT books_chk_available_lte_total 
        CHECK (available_copies <= total_copies)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table 7: book_issues
-- Records book loan transactions (issue, due date, return date, status)
CREATE TABLE IF NOT EXISTS book_issues (
    issue_id INT AUTO_INCREMENT PRIMARY KEY,
    book_id INT NOT NULL,
    student_id INT NOT NULL,
    librarian_id INT DEFAULT NULL,
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    return_date DATE DEFAULT NULL,
    status ENUM('Issued', 'Returned') NOT NULL DEFAULT 'Issued',
    CONSTRAINT fk_issues_book 
        FOREIGN KEY (book_id) REFERENCES books(book_id) 
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_issues_student 
        FOREIGN KEY (student_id) REFERENCES students(student_id) 
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_issues_librarian 
        FOREIGN KEY (librarian_id) REFERENCES librarians(librarian_id) 
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Table 8: fine_payments
-- Tracks overdue fines and payment statuses
CREATE TABLE IF NOT EXISTS fine_payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    issue_id INT NOT NULL,
    fine_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    payment_date DATE DEFAULT NULL,
    payment_status ENUM('Pending', 'Paid') NOT NULL DEFAULT 'Pending',
    CONSTRAINT fk_fines_issue 
        FOREIGN KEY (issue_id) REFERENCES book_issues(issue_id) 
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_fine_amount_non_negative 
        CHECK (fine_amount >= 0.00)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ============================================================================
-- 3. Database Views (DBMS Concept Demonstration)
-- ============================================================================

-- View 1: Detailed Book Catalog (Books + Author + Category + Stock)
CREATE OR REPLACE VIEW view_book_details AS
SELECT 
    b.book_id,
    b.title,
    b.isbn,
    b.publisher,
    b.total_copies,
    b.available_copies,
    (b.total_copies - b.available_copies) AS issued_copies,
    b.author_id,
    COALESCE(a.author_name, 'Unknown Author') AS author_name,
    b.category_id,
    COALESCE(c.category_name, 'General') AS category_name
FROM books b
LEFT JOIN authors a ON b.author_id = a.author_id
LEFT JOIN categories c ON b.category_id = c.category_id;

-- View 2: Issued Books Comprehensive Summary with Overdue Calculations
CREATE OR REPLACE VIEW view_issued_books_details AS
SELECT 
    bi.issue_id,
    bi.book_id,
    b.title AS book_title,
    b.isbn,
    bi.student_id,
    s.register_number,
    s.student_name,
    s.email AS student_email,
    d.department_name,
    bi.librarian_id,
    COALESCE(l.librarian_name, 'System') AS librarian_name,
    bi.issue_date,
    bi.due_date,
    bi.return_date,
    bi.status,
    GREATEST(0, DATEDIFF(COALESCE(bi.return_date, CURDATE()), bi.due_date)) AS overdue_days,
    fp.payment_id,
    COALESCE(fp.fine_amount, 
        CASE 
            WHEN DATEDIFF(COALESCE(bi.return_date, CURDATE()), bi.due_date) > 0 
            THEN DATEDIFF(COALESCE(bi.return_date, CURDATE()), bi.due_date) * 5.00 
            ELSE 0.00 
        END
    ) AS calculated_fine,
    COALESCE(fp.payment_status, 'No Fine') AS payment_status,
    fp.payment_date
FROM book_issues bi
INNER JOIN books b ON bi.book_id = b.book_id
INNER JOIN students s ON bi.student_id = s.student_id
LEFT JOIN departments d ON s.department_id = d.department_id
LEFT JOIN librarians l ON bi.librarian_id = l.librarian_id
LEFT JOIN fine_payments fp ON bi.issue_id = fp.issue_id;

-- View 3: Currently Overdue Books View
CREATE OR REPLACE VIEW view_overdue_books AS
SELECT * 
FROM view_issued_books_details
WHERE status = 'Issued' AND due_date < CURDATE();

-- View 4: Department-wise Issue Statistics (Demonstrating GROUP BY & Aggregates)
CREATE OR REPLACE VIEW view_department_issue_stats AS
SELECT 
    d.department_id,
    d.department_name,
    COUNT(DISTINCT s.student_id) AS total_students,
    COUNT(bi.issue_id) AS total_issues_count,
    COALESCE(SUM(CASE WHEN bi.status = 'Issued' THEN 1 ELSE 0 END), 0) AS active_issues_count,
    COALESCE(SUM(CASE WHEN bi.status = 'Returned' THEN 1 ELSE 0 END), 0) AS returned_count
FROM departments d
LEFT JOIN students s ON d.department_id = s.department_id
LEFT JOIN book_issues bi ON s.student_id = bi.student_id
GROUP BY d.department_id, d.department_name;

-- ============================================================================
-- 4. Triggers (Automating Inventory Consistency)
-- ============================================================================

-- Trigger 1: Prevent issuing a book when available copies <= 0
DROP TRIGGER IF EXISTS trg_prevent_negative_copies;
DELIMITER //
CREATE TRIGGER trg_prevent_negative_copies
BEFORE INSERT ON book_issues
FOR EACH ROW
BEGIN
    DECLARE v_available INT;
    SELECT available_copies INTO v_available FROM books WHERE book_id = NEW.book_id;
    IF v_available <= 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Cannot issue book: No available copies left in stock.';
    END IF;
END //
DELIMITER ;

-- Trigger 2: Automatically decrement available copies after a book issue
DROP TRIGGER IF EXISTS trg_decrement_copies_after_issue;
DELIMITER //
CREATE TRIGGER trg_decrement_copies_after_issue
AFTER INSERT ON book_issues
FOR EACH ROW
BEGIN
    UPDATE books 
    SET available_copies = available_copies - 1 
    WHERE book_id = NEW.book_id;
END //
DELIMITER ;

-- Trigger 3: Automatically increment available copies upon return
DROP TRIGGER IF EXISTS trg_increment_copies_after_return;
DELIMITER //
CREATE TRIGGER trg_increment_copies_after_return
AFTER UPDATE ON book_issues
FOR EACH ROW
BEGIN
    IF OLD.status = 'Issued' AND NEW.status = 'Returned' THEN
        UPDATE books 
        SET available_copies = available_copies + 1 
        WHERE book_id = NEW.book_id;
    END IF;
END //
DELIMITER ;

-- ============================================================================
-- 5. Stored Procedures (Demonstrating Business Logic & Transactions in DBMS)
-- ============================================================================

-- Procedure 1: Issue Book Procedure
DROP PROCEDURE IF EXISTS sp_issue_book;
DELIMITER //
CREATE PROCEDURE sp_issue_book(
    IN p_book_id INT,
    IN p_student_id INT,
    IN p_librarian_id INT,
    IN p_due_date DATE
)
BEGIN
    DECLARE v_available INT;
    SELECT available_copies INTO v_available FROM books WHERE book_id = p_book_id;
    
    IF v_available IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Book does not exist.';
    ELSEIF v_available <= 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No copies available for issue.';
    ELSE
        INSERT INTO book_issues (book_id, student_id, librarian_id, issue_date, due_date, status)
        VALUES (p_book_id, p_student_id, p_librarian_id, CURDATE(), p_due_date, 'Issued');
    END IF;
END //
DELIMITER ;

-- Procedure 2: Return Book and Compute Overdue Fine
DROP PROCEDURE IF EXISTS sp_return_book;
DELIMITER //
CREATE PROCEDURE sp_return_book(
    IN p_issue_id INT,
    IN p_fine_rate DECIMAL(10,2)
)
BEGIN
    DECLARE v_due_date DATE;
    DECLARE v_status VARCHAR(20);
    DECLARE v_days_overdue INT;
    DECLARE v_fine DECIMAL(10,2) DEFAULT 0.00;
    
    SELECT due_date, status INTO v_due_date, v_status FROM book_issues WHERE issue_id = p_issue_id;
    
    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Issue record not found.';
    ELSEIF v_status = 'Returned' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Book has already been returned.';
    ELSE
        -- Calculate overdue days
        SET v_days_overdue = DATEDIFF(CURDATE(), v_due_date);
        IF v_days_overdue > 0 THEN
            SET v_fine = v_days_overdue * p_fine_rate;
        ELSE
            SET v_fine = 0.00;
        END IF;
        
        -- Update issue record
        UPDATE book_issues 
        SET return_date = CURDATE(), status = 'Returned'
        WHERE issue_id = p_issue_id;
        
        -- Record fine if applicable
        IF v_fine > 0 THEN
            INSERT INTO fine_payments (issue_id, fine_amount, payment_status)
            VALUES (p_issue_id, v_fine, 'Pending');
        END IF;
    END IF;
END //
DELIMITER ;

-- ============================================================================
-- 6. Initial Seed Data
-- ============================================================================

-- Departments
INSERT IGNORE INTO departments (department_id, department_name) VALUES
(1, 'AIDS'),
(2, 'CSE'),
(3, 'ECE'),
(4, 'IT'),
(5, 'MECH');

-- Authors
INSERT IGNORE INTO authors (author_id, author_name) VALUES
(1, 'R. K. Narayan'),
(2, 'A. P. J. Abdul Kalam'),
(3, 'James Clear'),
(4, 'Stuart Russell & Peter Norvig'),
(5, 'Ian Goodfellow'),
(6, 'Abraham Silberschatz'),
(7, 'Robert C. Martin'),
(8, 'Wes McKinney');

-- Categories
INSERT IGNORE INTO categories (category_id, category_name) VALUES
(1, 'Computer Science'),
(2, 'Artificial Intelligence'),
(3, 'Fiction'),
(4, 'Self Development'),
(5, 'Machine Learning & Data Science'),
(6, 'Database Management Systems'),
(7, 'Software Engineering');

-- Librarians
INSERT IGNORE INTO librarians (librarian_id, librarian_name, phone, email) VALUES
(1, 'Admin Librarian', '9876543212', 'librarian@example.com');

-- Students
INSERT IGNORE INTO students (student_id, register_number, student_name, department_id, year_of_study, phone, email) VALUES
(1, 'STU001', 'Arun', 1, 2, '9876543210', 'arun@example.com'),
(2, 'STU002', 'Kumar', 2, 2, '9876543211', 'kumar@example.com'),
(3, 'STU003', 'Sneha Reddy', 1, 2, '9876543213', 'sneha.reddy@college.edu'),
(4, 'STU004', 'Priya Sharma', 4, 3, '9876543214', 'priya.sharma@college.edu'),
(5, 'STU005', 'Rahul Verma', 3, 1, '9876543215', 'rahul.verma@college.edu'),
(6, 'STU006', 'Ananya Iyer', 1, 2, '9876543216', 'ananya.iyer@college.edu');

-- Books
INSERT IGNORE INTO books (book_id, title, isbn, author_id, category_id, publisher, total_copies, available_copies) VALUES
(1, 'Wings of Fire', 'ISBN001', 2, 4, 'Universities Press', 5, 4),
(2, 'Atomic Habits', 'ISBN002', 3, 4, 'Random House', 4, 4),
(3, 'Computer Fundamentals', 'ISBN003', 1, 1, 'Tech Books', 3, 3),
(4, 'Artificial Intelligence: A Modern Approach', '978-0134610993', 4, 2, 'Pearson', 6, 6),
(5, 'Deep Learning', '978-0262035613', 5, 5, 'MIT Press', 5, 5),
(6, 'Database System Concepts', '978-0078022159', 6, 6, 'McGraw-Hill', 7, 6),
(7, 'Clean Code: A Handbook of Agile Software Craftsmanship', '978-0132350884', 7, 7, 'Prentice Hall', 4, 4),
(8, 'Python for Data Analysis', '978-1491957660', 8, 5, 'O Reilly Media', 5, 5);

-- Synchronize stock copies to ensure consistent inventory counts
UPDATE books b 
SET available_copies = total_copies - (
    SELECT COUNT(*) FROM book_issues bi WHERE bi.book_id = b.book_id AND bi.status = 'Issued'
);
