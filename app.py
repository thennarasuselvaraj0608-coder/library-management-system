import os
import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "library_mgmt_secret_key_aids_2026")


# ============================================================================
# Custom Jinja Filters
# ============================================================================
@app.template_filter("format_date")
def format_date(value, fmt="%d %b %Y"):
    if not value:
        return "-"
    if isinstance(value, str):
        try:
            value = datetime.datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return value
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime(fmt)
    return str(value)


@app.template_filter("currency")
def currency_filter(value):
    try:
        val = float(value or 0)
        return f"₹{val:,.2f}"
    except (ValueError, TypeError):
        return "₹0.00"


# Helper to sync book stock count idempotently
def sync_book_availability(book_id=None):
    try:
        if book_id:
            query = """
                UPDATE books b
                SET available_copies = GREATEST(0, total_copies - (
                    SELECT COUNT(*) FROM book_issues bi 
                    WHERE bi.book_id = b.book_id AND bi.status = 'Issued'
                ))
                WHERE b.book_id = %s;
            """
            db.execute_query(query, (book_id,), commit=True)
        else:
            query = """
                UPDATE books b
                SET available_copies = GREATEST(0, total_copies - (
                    SELECT COUNT(*) FROM book_issues bi 
                    WHERE bi.book_id = b.book_id AND bi.status = 'Issued'
                ));
            """
            db.execute_query(query, commit=True)
    except Exception as e:
        print(f"[SYNC WARNING] Could not sync book copies: {e}")


# ============================================================================
# Dashboard Route
# ============================================================================
@app.route("/")
def dashboard():
    try:
        # 1. Metric: Total Books & Total Copies
        book_stats = db.execute_query(
            """
            SELECT 
                COUNT(*) AS total_titles,
                COALESCE(SUM(total_copies), 0) AS total_copies,
                COALESCE(SUM(available_copies), 0) AS available_copies
            FROM books
            """,
            fetchone=True
        ) or {"total_titles": 0, "total_copies": 0, "available_copies": 0}

        # 2. Metric: Currently Issued Books
        issued_stats = db.execute_query(
            "SELECT COUNT(*) AS total_issued FROM book_issues WHERE status = 'Issued'",
            fetchone=True
        ) or {"total_issued": 0}

        # 3. Metric: Registered Students
        student_stats = db.execute_query(
            "SELECT COUNT(*) AS total_students FROM students",
            fetchone=True
        ) or {"total_students": 0}

        # 4. Metric: Overdue Books Count
        overdue_stats = db.execute_query(
            """
            SELECT COUNT(*) AS total_overdue 
            FROM book_issues 
            WHERE status = 'Issued' AND due_date < CURDATE()
            """,
            fetchone=True
        ) or {"total_overdue": 0}

        # 5. Metric: Fines Collected & Pending
        fine_stats = db.execute_query(
            """
            SELECT 
                COALESCE(SUM(CASE WHEN payment_status = 'Paid' THEN fine_amount ELSE 0 END), 0) AS collected,
                COALESCE(SUM(CASE WHEN payment_status = 'Pending' THEN fine_amount ELSE 0 END), 0) AS pending
            FROM fine_payments
            """,
            fetchone=True
        ) or {"collected": 0.0, "pending": 0.0}

        # 6. Chart 1: Books by Category (Demonstrating GROUP BY & INNER JOIN)
        cat_chart_data = db.execute_query(
            """
            SELECT 
                c.category_name, 
                COUNT(b.book_id) AS book_count,
                COALESCE(SUM(b.total_copies), 0) AS copy_count
            FROM categories c
            LEFT JOIN books b ON c.category_id = b.category_id
            GROUP BY c.category_id, c.category_name
            HAVING copy_count > 0
            ORDER BY copy_count DESC
            LIMIT 7
            """,
            fetchall=True
        ) or []

        # 7. Chart 2: Issues by Department (Demonstrating View Usage)
        dept_stats = db.execute_query(
            "SELECT department_name, total_students, total_issues_count, active_issues_count FROM view_department_issue_stats ORDER BY total_issues_count DESC",
            fetchall=True
        ) or []

        # 8. Recent Activities (Last 6 Issues)
        recent_issues = db.execute_query(
            """
            SELECT 
                issue_id, book_title, isbn, register_number, student_name, 
                department_name, issue_date, due_date, return_date, status, 
                overdue_days, calculated_fine, payment_status
            FROM view_issued_books_details 
            ORDER BY issue_id DESC 
            LIMIT 6
            """,
            fetchall=True
        ) or []

        # 9. Top Overdue Alerts (If any)
        urgent_overdue = db.execute_query(
            """
            SELECT issue_id, book_title, student_name, register_number, due_date, overdue_days, calculated_fine
            FROM view_overdue_books
            ORDER BY overdue_days DESC
            LIMIT 5
            """,
            fetchall=True
        ) or []

        return render_template(
            "index.html",
            total_titles=book_stats["total_titles"],
            total_copies=book_stats["total_copies"],
            available_copies=book_stats["available_copies"],
            issued_copies=issued_stats["total_issued"],
            total_students=student_stats["total_students"],
            overdue_count=overdue_stats["total_overdue"],
            fines_collected=fine_stats["collected"],
            fines_pending=fine_stats["pending"],
            cat_chart_data=cat_chart_data,
            dept_stats=dept_stats,
            recent_issues=recent_issues,
            urgent_overdue=urgent_overdue,
        )

    except Exception as e:
        flash(f"Error loading dashboard: {str(e)}", "danger")
        return render_template("index.html", error=str(e))


# ============================================================================
# Book Management Routes
# ============================================================================
@app.route("/books")
def list_books():
    search = request.args.get("search", "").strip()
    category_id = request.args.get("category_id", "").strip()
    availability = request.args.get("availability", "all").strip()

    # Base query using the view
    query = """
        SELECT 
            b.book_id, b.title, b.isbn, b.publisher, b.total_copies, 
            b.available_copies, b.issued_copies, b.author_name, b.category_name,
            b.category_id
        FROM view_book_details b
        WHERE 1=1
    """
    params = []

    if search:
        query += """
            AND (
                b.title LIKE %s OR 
                b.isbn LIKE %s OR 
                b.author_name LIKE %s OR 
                b.publisher LIKE %s
            )
        """
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param, search_param])

    if category_id and category_id.isdigit():
        query += " AND b.category_id = %s"
        params.append(int(category_id))

    if availability == "available":
        query += " AND b.available_copies > 0"
    elif availability == "out_of_stock":
        query += " AND b.available_copies = 0"

    query += " ORDER BY b.title ASC"

    try:
        books = db.execute_query(query, params, fetchall=True) or []
        categories = db.execute_query("SELECT category_id, category_name FROM categories ORDER BY category_name ASC", fetchall=True) or []
        return render_template("books.html", books=books, categories=categories, search=search, selected_cat=category_id, availability=availability)
    except Exception as e:
        flash(f"Error retrieving books: {str(e)}", "danger")
        return render_template("books.html", books=[], categories=[], search=search, selected_cat="", availability=availability)


@app.route("/books/add", methods=["GET", "POST"])
def add_book():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        isbn = request.form.get("isbn", "").strip()
        publisher = request.form.get("publisher", "").strip()
        total_copies = request.form.get("total_copies", "1").strip()
        author_id = request.form.get("author_id", "").strip()
        new_author = request.form.get("new_author", "").strip()
        category_id = request.form.get("category_id", "").strip()
        new_category = request.form.get("new_category", "").strip()

        # Validation
        if not title:
            flash("Book title is required.", "warning")
            return redirect(url_for("add_book"))

        try:
            total_copies = int(total_copies)
            if total_copies < 1:
                flash("Total copies must be at least 1.", "warning")
                return redirect(url_for("add_book"))
        except ValueError:
            flash("Invalid number of copies.", "warning")
            return redirect(url_for("add_book"))

        try:
            # Check unique ISBN if provided
            if isbn:
                existing_isbn = db.execute_query("SELECT book_id FROM books WHERE isbn = %s", (isbn,), fetchone=True)
                if existing_isbn:
                    flash(f"A book with ISBN '{isbn}' already exists in the catalog.", "danger")
                    return redirect(url_for("add_book"))

            # Handle author (new or existing)
            final_author_id = None
            if new_author:
                author_row = db.execute_query("SELECT author_id FROM authors WHERE author_name = %s", (new_author,), fetchone=True)
                if author_row:
                    final_author_id = author_row["author_id"]
                else:
                    final_author_id = db.execute_query("INSERT INTO authors (author_name) VALUES (%s)", (new_author,), commit=True)
            elif author_id and author_id.isdigit():
                final_author_id = int(author_id)

            # Handle category (new or existing)
            final_cat_id = None
            if new_category:
                cat_row = db.execute_query("SELECT category_id FROM categories WHERE category_name = %s", (new_category,), fetchone=True)
                if cat_row:
                    final_cat_id = cat_row["category_id"]
                else:
                    final_cat_id = db.execute_query("INSERT INTO categories (category_name) VALUES (%s)", (new_category,), commit=True)
            elif category_id and category_id.isdigit():
                final_cat_id = int(category_id)

            # Insert book record
            insert_query = """
                INSERT INTO books (title, isbn, author_id, category_id, publisher, total_copies, available_copies)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            new_book_id = db.execute_query(
                insert_query,
                (title, isbn or None, final_author_id, final_cat_id, publisher or None, total_copies, total_copies),
                commit=True
            )

            flash(f"Book '{title}' added successfully to inventory!", "success")
            return redirect(url_for("list_books"))

        except Exception as e:
            flash(f"Database error while adding book: {str(e)}", "danger")
            return redirect(url_for("add_book"))

    # GET Request: Load authors and categories
    try:
        authors = db.execute_query("SELECT author_id, author_name FROM authors ORDER BY author_name ASC", fetchall=True) or []
        categories = db.execute_query("SELECT category_id, category_name FROM categories ORDER BY category_name ASC", fetchall=True) or []
        return render_template("add_book.html", authors=authors, categories=categories)
    except Exception as e:
        flash(f"Error loading form options: {str(e)}", "danger")
        return render_template("add_book.html", authors=[], categories=[])


@app.route("/books/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    book = db.execute_query("SELECT * FROM books WHERE book_id = %s", (book_id,), fetchone=True)
    if not book:
        flash("Book not found.", "danger")
        return redirect(url_for("list_books"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        isbn = request.form.get("isbn", "").strip()
        publisher = request.form.get("publisher", "").strip()
        total_copies = request.form.get("total_copies", "1").strip()
        author_id = request.form.get("author_id", "").strip()
        new_author = request.form.get("new_author", "").strip()
        category_id = request.form.get("category_id", "").strip()
        new_category = request.form.get("new_category", "").strip()

        if not title:
            flash("Book title cannot be blank.", "warning")
            return redirect(url_for("edit_book", book_id=book_id))

        try:
            new_total = int(total_copies)
            # Find how many copies are currently issued
            active_issues_count = db.execute_query(
                "SELECT COUNT(*) AS active_count FROM book_issues WHERE book_id = %s AND status = 'Issued'",
                (book_id,),
                fetchone=True
            )["active_count"]

            if new_total < active_issues_count:
                flash(f"Cannot set total copies to {new_total}. There are currently {active_issues_count} copies on loan!", "danger")
                return redirect(url_for("edit_book", book_id=book_id))

            # Check unique ISBN collision
            if isbn and isbn != book.get("isbn"):
                existing = db.execute_query("SELECT book_id FROM books WHERE isbn = %s AND book_id != %s", (isbn, book_id), fetchone=True)
                if existing:
                    flash(f"Another book with ISBN '{isbn}' already exists.", "danger")
                    return redirect(url_for("edit_book", book_id=book_id))

            # Author handling
            final_author_id = book.get("author_id")
            if new_author:
                author_row = db.execute_query("SELECT author_id FROM authors WHERE author_name = %s", (new_author,), fetchone=True)
                if author_row:
                    final_author_id = author_row["author_id"]
                else:
                    final_author_id = db.execute_query("INSERT INTO authors (author_name) VALUES (%s)", (new_author,), commit=True)
            elif author_id and author_id.isdigit():
                final_author_id = int(author_id)

            # Category handling
            final_cat_id = book.get("category_id")
            if new_category:
                cat_row = db.execute_query("SELECT category_id FROM categories WHERE category_name = %s", (new_category,), fetchone=True)
                if cat_row:
                    final_cat_id = cat_row["category_id"]
                else:
                    final_cat_id = db.execute_query("INSERT INTO categories (category_name) VALUES (%s)", (new_category,), commit=True)
            elif category_id and category_id.isdigit():
                final_cat_id = int(category_id)

            # New available copies calculation
            new_available = new_total - active_issues_count

            update_query = """
                UPDATE books
                SET title = %s, isbn = %s, author_id = %s, category_id = %s,
                    publisher = %s, total_copies = %s, available_copies = %s
                WHERE book_id = %s
            """
            db.execute_query(
                update_query,
                (title, isbn or None, final_author_id, final_cat_id, publisher or None, new_total, new_available, book_id),
                commit=True
            )

            flash(f"Book '{title}' updated successfully!", "success")
            return redirect(url_for("list_books"))

        except Exception as e:
            flash(f"Error updating book: {str(e)}", "danger")
            return redirect(url_for("edit_book", book_id=book_id))

    # GET Request
    authors = db.execute_query("SELECT author_id, author_name FROM authors ORDER BY author_name ASC", fetchall=True) or []
    categories = db.execute_query("SELECT category_id, category_name FROM categories ORDER BY category_name ASC", fetchall=True) or []
    return render_template("edit_book.html", book=book, authors=authors, categories=categories)


@app.route("/books/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    try:
        # Check if copies are currently issued
        active_issues = db.execute_query(
            "SELECT COUNT(*) AS active_count FROM book_issues WHERE book_id = %s AND status = 'Issued'",
            (book_id,),
            fetchone=True
        )["active_count"]

        if active_issues > 0:
            flash(f"Cannot delete book: {active_issues} copy/copies are currently issued to students. They must be returned first.", "danger")
            return redirect(url_for("list_books"))

        # Delete historical issues & fines if any, safely using transaction
        operations = [
            ("DELETE FROM fine_payments WHERE issue_id IN (SELECT issue_id FROM book_issues WHERE book_id = %s)", (book_id,)),
            ("DELETE FROM book_issues WHERE book_id = %s", (book_id,)),
            ("DELETE FROM books WHERE book_id = %s", (book_id,))
        ]
        db.execute_transaction(operations)

        flash("Book deleted from library records.", "info")
    except Exception as e:
        flash(f"Failed to delete book: {str(e)}", "danger")

    return redirect(url_for("list_books"))


# ============================================================================
# Student Management Routes
# ============================================================================
@app.route("/students")
def list_students():
    search = request.args.get("search", "").strip()
    dept_id = request.args.get("department_id", "").strip()

    query = """
        SELECT 
            s.student_id, s.register_number, s.student_name, s.department_id,
            d.department_name, s.year_of_study, s.phone, s.email,
            COUNT(CASE WHEN bi.status = 'Issued' THEN 1 END) AS active_borrowed_books,
            COUNT(bi.issue_id) AS total_history_issues
        FROM students s
        LEFT JOIN departments d ON s.department_id = d.department_id
        LEFT JOIN book_issues bi ON s.student_id = bi.student_id
        WHERE 1=1
    """
    params = []

    if search:
        query += """
            AND (
                s.student_name LIKE %s OR 
                s.register_number LIKE %s OR 
                s.email LIKE %s OR 
                s.phone LIKE %s
            )
        """
        sp = f"%{search}%"
        params.extend([sp, sp, sp, sp])

    if dept_id and dept_id.isdigit():
        query += " AND s.department_id = %s"
        params.append(int(dept_id))

    query += " GROUP BY s.student_id, d.department_name ORDER BY s.student_name ASC"

    try:
        students = db.execute_query(query, params, fetchall=True) or []
        departments = db.execute_query("SELECT department_id, department_name FROM departments ORDER BY department_name ASC", fetchall=True) or []
        return render_template("students.html", students=students, departments=departments, search=search, selected_dept=dept_id)
    except Exception as e:
        flash(f"Error retrieving students: {str(e)}", "danger")
        return render_template("students.html", students=[], departments=[], search=search, selected_dept="")


@app.route("/students/add", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        register_number = request.form.get("register_number", "").strip().upper()
        student_name = request.form.get("student_name", "").strip()
        department_id = request.form.get("department_id", "").strip()
        year_of_study = request.form.get("year_of_study", "1").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        if not register_number or not student_name:
            flash("Register number and student name are required.", "warning")
            return redirect(url_for("add_student"))

        try:
            year_of_study = int(year_of_study)
            if not (1 <= year_of_study <= 4):
                flash("Year of study must be between 1 and 4.", "warning")
                return redirect(url_for("add_student"))
        except ValueError:
            flash("Year of study must be a number (1-4).", "warning")
            return redirect(url_for("add_student"))

        try:
            # Check duplicate register number
            dup_reg = db.execute_query("SELECT student_id FROM students WHERE register_number = %s", (register_number,), fetchone=True)
            if dup_reg:
                flash(f"A student with register number '{register_number}' is already registered.", "danger")
                return redirect(url_for("add_student"))

            # Check duplicate email
            if email:
                dup_email = db.execute_query("SELECT student_id FROM students WHERE email = %s", (email,), fetchone=True)
                if dup_email:
                    flash(f"Email '{email}' is already in use.", "danger")
                    return redirect(url_for("add_student"))

            dept_val = int(department_id) if department_id and department_id.isdigit() else None

            insert_query = """
                INSERT INTO students (register_number, student_name, department_id, year_of_study, phone, email)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            db.execute_query(insert_query, (register_number, student_name, dept_val, year_of_study, phone or None, email or None), commit=True)

            flash(f"Student '{student_name}' ({register_number}) registered successfully!", "success")
            return redirect(url_for("list_students"))

        except Exception as e:
            flash(f"Error registering student: {str(e)}", "danger")
            return redirect(url_for("add_student"))

    departments = db.execute_query("SELECT department_id, department_name FROM departments ORDER BY department_name ASC", fetchall=True) or []
    return render_template("add_student.html", departments=departments)


@app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
def edit_student(student_id):
    student = db.execute_query("SELECT * FROM students WHERE student_id = %s", (student_id,), fetchone=True)
    if not student:
        flash("Student record not found.", "danger")
        return redirect(url_for("list_students"))

    if request.method == "POST":
        register_number = request.form.get("register_number", "").strip().upper()
        student_name = request.form.get("student_name", "").strip()
        department_id = request.form.get("department_id", "").strip()
        year_of_study = request.form.get("year_of_study", "1").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()

        if not register_number or not student_name:
            flash("Register number and student name are required.", "warning")
            return redirect(url_for("edit_student", student_id=student_id))

        try:
            year_of_study = int(year_of_study)
        except ValueError:
            year_of_study = 1

        try:
            # Check register number collisions with other students
            dup_reg = db.execute_query("SELECT student_id FROM students WHERE register_number = %s AND student_id != %s", (register_number, student_id), fetchone=True)
            if dup_reg:
                flash(f"Register number '{register_number}' belongs to another student.", "danger")
                return redirect(url_for("edit_student", student_id=student_id))

            # Check email collisions
            if email:
                dup_email = db.execute_query("SELECT student_id FROM students WHERE email = %s AND student_id != %s", (email, student_id), fetchone=True)
                if dup_email:
                    flash(f"Email '{email}' is used by another record.", "danger")
                    return redirect(url_for("edit_student", student_id=student_id))

            dept_val = int(department_id) if department_id and department_id.isdigit() else None

            update_query = """
                UPDATE students
                SET register_number = %s, student_name = %s, department_id = %s,
                    year_of_study = %s, phone = %s, email = %s
                WHERE student_id = %s
            """
            db.execute_query(update_query, (register_number, student_name, dept_val, year_of_study, phone or None, email or None, student_id), commit=True)

            flash(f"Student '{student_name}' record updated successfully!", "success")
            return redirect(url_for("list_students"))

        except Exception as e:
            flash(f"Error updating student: {str(e)}", "danger")
            return redirect(url_for("edit_student", student_id=student_id))

    departments = db.execute_query("SELECT department_id, department_name FROM departments ORDER BY department_name ASC", fetchall=True) or []
    return render_template("edit_student.html", student=student, departments=departments)


@app.route("/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    try:
        # Check active borrowed books
        active = db.execute_query("SELECT COUNT(*) AS active_count FROM book_issues WHERE student_id = %s AND status = 'Issued'", (student_id,), fetchone=True)["active_count"]
        if active > 0:
            flash(f"Cannot delete student: The student currently holds {active} unreturned library book(s).", "danger")
            return redirect(url_for("list_students"))

        # Delete fine records and issue history
        operations = [
            ("DELETE FROM fine_payments WHERE issue_id IN (SELECT issue_id FROM book_issues WHERE student_id = %s)", (student_id,)),
            ("DELETE FROM book_issues WHERE student_id = %s", (student_id,)),
            ("DELETE FROM students WHERE student_id = %s", (student_id,))
        ]
        db.execute_transaction(operations)

        flash("Student deleted successfully.", "info")
    except Exception as e:
        flash(f"Error deleting student: {str(e)}", "danger")

    return redirect(url_for("list_students"))


@app.route("/students/<int:student_id>/history")
def student_history(student_id):
    student = db.execute_query(
        """
        SELECT s.*, d.department_name 
        FROM students s 
        LEFT JOIN departments d ON s.department_id = d.department_id 
        WHERE s.student_id = %s
        """,
        (student_id,),
        fetchone=True
    )
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("list_students"))

    history = db.execute_query(
        """
        SELECT * FROM view_issued_books_details 
        WHERE student_id = %s 
        ORDER BY issue_id DESC
        """,
        (student_id,),
        fetchall=True
    ) or []

    return render_template("student_history.html", student=student, history=history)


# ============================================================================
# Book Issue and Return Routes
# ============================================================================
@app.route("/issue", methods=["GET", "POST"])
def issue_book():
    if request.method == "POST":
        book_id = request.form.get("book_id", "").strip()
        student_id = request.form.get("student_id", "").strip()
        librarian_id = request.form.get("librarian_id", "1").strip()
        issue_date_str = request.form.get("issue_date", "").strip()
        due_date_str = request.form.get("due_date", "").strip()

        if not book_id or not student_id:
            flash("Please select both a book and a student.", "warning")
            return redirect(url_for("issue_book"))

        try:
            b_id = int(book_id)
            s_id = int(student_id)
            lib_id = int(librarian_id) if librarian_id and librarian_id.isdigit() else 1

            # 1. Check book availability
            book_info = db.execute_query("SELECT title, available_copies FROM books WHERE book_id = %s", (b_id,), fetchone=True)
            if not book_info:
                flash("Selected book does not exist in the database.", "danger")
                return redirect(url_for("issue_book"))

            if book_info["available_copies"] <= 0:
                flash(f"Sorry, '{book_info['title']}' has 0 available copies left in stock.", "warning")
                return redirect(url_for("issue_book"))

            # 2. Check student validity & active borrowing quota (max 3 books per student)
            student_info = db.execute_query("SELECT student_name, register_number FROM students WHERE student_id = %s", (s_id,), fetchone=True)
            if not student_info:
                flash("Selected student not found.", "danger")
                return redirect(url_for("issue_book"))

            current_borrowed = db.execute_query(
                "SELECT COUNT(*) AS active_count FROM book_issues WHERE student_id = %s AND status = 'Issued'",
                (s_id,),
                fetchone=True
            )["active_count"]

            MAX_BORROW_LIMIT = 4
            if current_borrowed >= MAX_BORROW_LIMIT:
                flash(f"Student {student_info['student_name']} already has {current_borrowed} active borrowed books (Maximum limit is {MAX_BORROW_LIMIT}). Please return existing books first.", "warning")
                return redirect(url_for("issue_book"))

            # 3. Parse and validate issue and due dates
            today = datetime.date.today()
            if issue_date_str:
                issue_date = datetime.datetime.strptime(issue_date_str, "%Y-%m-%d").date()
            else:
                issue_date = today

            if due_date_str:
                due_date = datetime.datetime.strptime(due_date_str, "%Y-%m-%d").date()
            else:
                due_date = issue_date + datetime.timedelta(days=14)

            if due_date < issue_date:
                flash("Due date cannot be before the issue date.", "warning")
                return redirect(url_for("issue_book"))

            # 4. Perform Transaction: Insert into book_issues and decrement available_copies
            operations = [
                (
                    """
                    INSERT INTO book_issues (book_id, student_id, librarian_id, issue_date, due_date, status)
                    VALUES (%s, %s, %s, %s, %s, 'Issued')
                    """,
                    (b_id, s_id, lib_id, issue_date, due_date)
                ),
                (
                    """
                    UPDATE books 
                    SET available_copies = GREATEST(0, available_copies - 1) 
                    WHERE book_id = %s
                    """,
                    (b_id,)
                )
            ]
            db.execute_transaction(operations)
            sync_book_availability(b_id)

            flash(f"Success! '{book_info['title']}' issued to {student_info['student_name']} ({student_info['register_number']}). Due Date: {due_date.strftime('%d %b %Y')}.", "success")
            return redirect(url_for("list_issued_books"))

        except Exception as e:
            flash(f"Failed to issue book: {str(e)}", "danger")
            return redirect(url_for("issue_book"))

    # GET Request: Prepare selection lists
    preset_book_id = request.args.get("book_id", "")
    preset_student_id = request.args.get("student_id", "")

    # Only show books with available copies > 0 (or include preset book)
    books = db.execute_query(
        """
        SELECT b.book_id, b.title, b.isbn, b.available_copies, b.total_copies, a.author_name
        FROM books b
        LEFT JOIN authors a ON b.author_id = a.author_id
        WHERE b.available_copies > 0 OR b.book_id = %s
        ORDER BY b.title ASC
        """,
        (int(preset_book_id) if preset_book_id and preset_book_id.isdigit() else 0,),
        fetchall=True
    ) or []

    students = db.execute_query(
        """
        SELECT s.student_id, s.register_number, s.student_name, d.department_name
        FROM students s
        LEFT JOIN departments d ON s.department_id = d.department_id
        ORDER BY s.student_name ASC
        """,
        fetchall=True
    ) or []

    librarians = db.execute_query("SELECT librarian_id, librarian_name FROM librarians", fetchall=True) or []

    default_issue_date = datetime.date.today().strftime("%Y-%m-%d")
    default_due_date = (datetime.date.today() + datetime.timedelta(days=14)).strftime("%Y-%m-%d")

    return render_template(
        "issue_book.html",
        books=books,
        students=students,
        librarians=librarians,
        default_issue_date=default_issue_date,
        default_due_date=default_due_date,
        preset_book_id=preset_book_id,
        preset_student_id=preset_student_id,
    )


@app.route("/issued-books")
def list_issued_books():
    tab = request.args.get("tab", "active").strip().lower()
    search = request.args.get("search", "").strip()

    query = """
        SELECT * FROM view_issued_books_details
        WHERE 1=1
    """
    params = []

    if tab == "active":
        query += " AND status = 'Issued'"
    elif tab == "overdue":
        query += " AND status = 'Issued' AND due_date < CURDATE()"
    elif tab == "returned":
        query += " AND status = 'Returned'"

    if search:
        query += """
            AND (
                book_title LIKE %s OR 
                isbn LIKE %s OR 
                student_name LIKE %s OR 
                register_number LIKE %s
            )
        """
        sp = f"%{search}%"
        params.extend([sp, sp, sp, sp])

    query += " ORDER BY issue_id DESC"

    try:
        issues = db.execute_query(query, params, fetchall=True) or []

        # Count summary for badges
        counts = {
            "all": db.execute_query("SELECT COUNT(*) AS c FROM book_issues", fetchone=True)["c"],
            "active": db.execute_query("SELECT COUNT(*) AS c FROM book_issues WHERE status = 'Issued'", fetchone=True)["c"],
            "overdue": db.execute_query("SELECT COUNT(*) AS c FROM book_issues WHERE status = 'Issued' AND due_date < CURDATE()", fetchone=True)["c"],
            "returned": db.execute_query("SELECT COUNT(*) AS c FROM book_issues WHERE status = 'Returned'", fetchone=True)["c"],
        }

        return render_template("issued_books.html", issues=issues, tab=tab, search=search, counts=counts)
    except Exception as e:
        flash(f"Error retrieving issued books: {str(e)}", "danger")
        return render_template("issued_books.html", issues=[], tab=tab, search=search, counts={"all": 0, "active": 0, "overdue": 0, "returned": 0})


@app.route("/return/<int:issue_id>", methods=["POST"])
def return_book(issue_id):
    try:
        # 1. Fetch issue details
        issue = db.execute_query("SELECT * FROM view_issued_books_details WHERE issue_id = %s", (issue_id,), fetchone=True)
        if not issue:
            flash("Book loan record not found.", "danger")
            return redirect(url_for("list_issued_books"))

        if issue["status"] == "Returned":
            flash("This book has already been returned.", "info")
            return redirect(url_for("list_issued_books"))

        today = datetime.date.today()
        due_date = issue["due_date"]
        book_id = issue["book_id"]

        # Calculate overdue days and fine (₹5 per overdue day)
        overdue_days = max(0, (today - due_date).days)
        fine_rate_per_day = 5.00
        fine_amount = overdue_days * fine_rate_per_day

        paid_now = request.form.get("paid_now", "no") == "yes"

        # 2. Perform ACID Transaction
        operations = [
            (
                """
                UPDATE book_issues 
                SET return_date = %s, status = 'Returned' 
                WHERE issue_id = %s
                """,
                (today, issue_id)
            ),
            (
                """
                UPDATE books 
                SET available_copies = LEAST(total_copies, available_copies + 1) 
                WHERE book_id = %s
                """,
                (book_id,)
            )
        ]

        # Handle fine record
        if fine_amount > 0:
            payment_status = "Paid" if paid_now else "Pending"
            payment_date = today if paid_now else None

            # Check if fine record already exists
            existing_fine = db.execute_query("SELECT payment_id FROM fine_payments WHERE issue_id = %s", (issue_id,), fetchone=True)
            if existing_fine:
                operations.append((
                    """
                    UPDATE fine_payments 
                    SET fine_amount = %s, payment_date = %s, payment_status = %s 
                    WHERE issue_id = %s
                    """,
                    (fine_amount, payment_date, payment_status, issue_id)
                ))
            else:
                operations.append((
                    """
                    INSERT INTO fine_payments (issue_id, fine_amount, payment_date, payment_status)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (issue_id, fine_amount, payment_date, payment_status)
                ))

        db.execute_transaction(operations)
        sync_book_availability(book_id)

        if fine_amount > 0:
            status_text = "PAID on spot" if paid_now else "recorded as PENDING"
            flash(f"Book '{issue['book_title']}' returned successfully! Overdue by {overdue_days} days. Fine of ₹{fine_amount:.2f} is {status_text}.", "warning" if not paid_now else "success")
        else:
            flash(f"Book '{issue['book_title']}' returned successfully on time! No fine incurred.", "success")

    except Exception as e:
        flash(f"Failed to record book return: {str(e)}", "danger")

    return redirect(url_for("list_issued_books"))


@app.route("/fines/pay/<int:payment_id>", methods=["POST"])
def pay_fine(payment_id):
    try:
        today = datetime.date.today()
        db.execute_query(
            "UPDATE fine_payments SET payment_status = 'Paid', payment_date = %s WHERE payment_id = %s",
            (today, payment_id),
            commit=True
        )
        flash("Fine payment marked as PAID successfully!", "success")
    except Exception as e:
        flash(f"Error updating payment record: {str(e)}", "danger")

    # Redirect back to referring page or reports
    referrer = request.referrer or url_for("reports")
    return redirect(referrer)


# ============================================================================
# Reports Route
# ============================================================================
@app.route("/reports")
def reports():
    tab = request.args.get("tab", "issued").strip().lower()
    student_filter = request.args.get("student_id", "").strip()

    try:
        # Report 1: Currently Issued Books
        active_issued = db.execute_query(
            "SELECT * FROM view_issued_books_details WHERE status = 'Issued' ORDER BY due_date ASC",
            fetchall=True
        ) or []

        # Report 2: Overdue Books
        overdue_books = db.execute_query(
            "SELECT * FROM view_overdue_books ORDER BY overdue_days DESC",
            fetchall=True
        ) or []

        # Report 3: Borrowing History
        history_query = "SELECT * FROM view_issued_books_details WHERE 1=1"
        history_params = []
        if student_filter and student_filter.isdigit():
            history_query += " AND student_id = %s"
            history_params.append(int(student_filter))
        history_query += " ORDER BY issue_id DESC"
        borrow_history = db.execute_query(history_query, history_params, fetchall=True) or []

        # Report 4: Fine Payments Log
        fine_log = db.execute_query(
            """
            SELECT 
                fp.payment_id, fp.issue_id, fp.fine_amount, fp.payment_date, fp.payment_status,
                b.title AS book_title, s.student_name, s.register_number, bi.due_date, bi.return_date
            FROM fine_payments fp
            JOIN book_issues bi ON fp.issue_id = bi.issue_id
            JOIN books b ON bi.book_id = b.book_id
            JOIN students s ON bi.student_id = s.student_id
            ORDER BY fp.payment_id DESC
            """,
            fetchall=True
        ) or []

        # Report 5: Category & Department Analytics (GROUP BY, HAVING, AGGREGATES)
        dept_analytics = db.execute_query(
            "SELECT * FROM view_department_issue_stats ORDER BY total_issues_count DESC",
            fetchall=True
        ) or []

        cat_analytics = db.execute_query(
            """
            SELECT 
                c.category_id,
                c.category_name,
                COUNT(b.book_id) AS total_titles,
                COALESCE(SUM(b.total_copies), 0) AS total_copies,
                COALESCE(SUM(b.available_copies), 0) AS available_copies,
                COALESCE(SUM(b.total_copies - b.available_copies), 0) AS issued_copies
            FROM categories c
            LEFT JOIN books b ON c.category_id = b.category_id
            GROUP BY c.category_id, c.category_name
            ORDER BY total_copies DESC
            """,
            fetchall=True
        ) or []

        # Fine Summary Cards
        fines_summary = db.execute_query(
            """
            SELECT 
                COALESCE(SUM(CASE WHEN payment_status = 'Paid' THEN fine_amount ELSE 0 END), 0) AS total_collected,
                COALESCE(SUM(CASE WHEN payment_status = 'Pending' THEN fine_amount ELSE 0 END), 0) AS total_pending,
                COUNT(CASE WHEN payment_status = 'Pending' THEN 1 END) AS pending_count
            FROM fine_payments
            """,
            fetchone=True
        ) or {"total_collected": 0, "total_pending": 0, "pending_count": 0}

        students_list = db.execute_query("SELECT student_id, register_number, student_name FROM students ORDER BY student_name ASC", fetchall=True) or []

        return render_template(
            "reports.html",
            tab=tab,
            active_issued=active_issued,
            overdue_books=overdue_books,
            borrow_history=borrow_history,
            fine_log=fine_log,
            dept_analytics=dept_analytics,
            cat_analytics=cat_analytics,
            fines_summary=fines_summary,
            students_list=students_list,
            selected_student=student_filter,
        )

    except Exception as e:
        flash(f"Error generating reports: {str(e)}", "danger")
        return render_template("reports.html", tab=tab, error=str(e))


# ============================================================================
# API Endpoints (For Charts & Health)
# ============================================================================
@app.route("/api/chart-data")
def api_chart_data():
    try:
        cat_data = db.execute_query(
            """
            SELECT c.category_name, COALESCE(SUM(b.total_copies), 0) AS copies
            FROM categories c
            JOIN books b ON c.category_id = b.category_id
            GROUP BY c.category_id, c.category_name
            HAVING copies > 0
            ORDER BY copies DESC
            """,
            fetchall=True
        ) or []

        dept_data = db.execute_query(
            "SELECT department_name, total_issues_count FROM view_department_issue_stats",
            fetchall=True
        ) or []

        return jsonify({
            "status": "success",
            "categories": [r["category_name"] for r in cat_data],
            "category_copies": [int(r["copies"]) for r in cat_data],
            "departments": [r["department_name"] for r in dept_data],
            "department_issues": [int(r["total_issues_count"]) for r in dept_data]
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health")
def health_check():
    connected, msg = db.test_connection()
    return jsonify({
        "database_connected": connected,
        "database_message": msg,
        "app_status": "running"
    })


# ============================================================================
# Error Handlers
# ============================================================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template("base.html", not_found=True), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("base.html", server_error=True), 500


if __name__ == "__main__":
    # Ensure all copies counts are synced at startup
    sync_book_availability()
    print("=" * 60)
    print(" Automated Library Book Tracking and Management System")
    print(" Running at http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host="127.0.0.1", port=5000)
