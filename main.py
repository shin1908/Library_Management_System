import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from datetime import date, timedelta

DB_FILE = "library.db"
LOAN_DAYS = 14

class Database:
    def __init__(self, path=DB_FILE):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.create_tables()

    def create_tables(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    title     TEXT NOT NULL,
                    author    TEXT NOT NULL,
                    isbn      TEXT UNIQUE,
                    quantity  INTEGER NOT NULL,
                    available INTEGER NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issues (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id     INTEGER NOT NULL,
                    member_name TEXT NOT NULL,
                    issue_date  TEXT NOT NULL,
                    due_date    TEXT NOT NULL,
                    return_date TEXT,
                    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
                )
                """
            )

    def add_book(self, title, author, isbn, quantity):
        with self.conn:
            self.conn.execute(
                "INSERT INTO books (title, author, isbn, quantity, available) "
                "VALUES (?, ?, ?, ?, ?)",
                (title, author, isbn or None, quantity, quantity),
            )

    def get_books(self, search=""):
        like = f"%{search}%"
        cur = self.conn.execute(
            "SELECT id, title, author, isbn, quantity, available FROM books "
            "WHERE title LIKE ? OR author LIKE ? OR IFNULL(isbn, '') LIKE ? "
            "ORDER BY title COLLATE NOCASE",
            (like, like, like),
        )
        return cur.fetchall()

    def delete_book(self, book_id):
        with self.conn:
            self.conn.execute("DELETE FROM books WHERE id = ?", (book_id,))

    def active_issue_count(self, book_id):
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM issues WHERE book_id = ? AND return_date IS NULL",
            (book_id,),
        )
        return cur.fetchone()[0]

   
    def issue_book(self, book_id, member_name):
        cur = self.conn.execute("SELECT available FROM books WHERE id = ?", (book_id,))
        row = cur.fetchone()
        if row is None or row[0] <= 0:
            return False
        today = date.today()
        due = today + timedelta(days=LOAN_DAYS)
        with self.conn:
            self.conn.execute(
                "INSERT INTO issues (book_id, member_name, issue_date, due_date) "
                "VALUES (?, ?, ?, ?)",
                (book_id, member_name, today.isoformat(), due.isoformat()),
            )
            self.conn.execute(
                "UPDATE books SET available = available - 1 WHERE id = ?", (book_id,)
            )
        return True

    def return_book(self, issue_id):
        cur = self.conn.execute(
            "SELECT book_id FROM issues WHERE id = ? AND return_date IS NULL",
            (issue_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        with self.conn:
            self.conn.execute(
                "UPDATE issues SET return_date = ? WHERE id = ?",
                (date.today().isoformat(), issue_id),
            )
            self.conn.execute(
                "UPDATE books SET available = available + 1 WHERE id = ?", (row[0],)
            )
        return True

    def get_active_issues(self):
        cur = self.conn.execute(
            "SELECT i.id, b.title, i.member_name, i.issue_date, i.due_date "
            "FROM issues i JOIN books b ON b.id = i.book_id "
            "WHERE i.return_date IS NULL ORDER BY i.due_date"
        )
        return cur.fetchall()


class LibraryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Library Management System")
        self.geometry("850x560")
        self.minsize(750, 480)

        self.db = Database()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.books_tab = ttk.Frame(notebook)
        self.issued_tab = ttk.Frame(notebook)
        notebook.add(self.books_tab, text="  Books  ")
        notebook.add(self.issued_tab, text="  Issued Books  ")

        self.build_books_tab()
        self.build_issued_tab()

        self.refresh_books()
        self.refresh_issues()

   
    def build_books_tab(self):
        # Add-book form
        form = ttk.LabelFrame(self.books_tab, text="Add New Book")
        form.pack(fill="x", padx=8, pady=8)

        self.title_var = tk.StringVar()
        self.author_var = tk.StringVar()
        self.isbn_var = tk.StringVar()
        self.qty_var = tk.StringVar(value="1")

        fields = [
            ("Title", self.title_var, 28),
            ("Author", self.author_var, 22),
            ("ISBN", self.isbn_var, 16),
            ("Qty", self.qty_var, 5),
        ]
        for col, (label, var, width) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=0, column=col, padx=6, pady=(6, 0), sticky="w")
            ttk.Entry(form, textvariable=var, width=width).grid(
                row=1, column=col, padx=6, pady=(0, 8), sticky="w"
            )
        ttk.Button(form, text="Add Book", command=self.add_book).grid(
            row=1, column=len(fields), padx=8, pady=(0, 8)
        )

        search_frame = ttk.Frame(self.books_tab)
        search_frame.pack(fill="x", padx=8)
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_books())
        ttk.Entry(search_frame, textvariable=self.search_var, width=35).pack(
            side="left", padx=6
        )

        cols = ("id", "title", "author", "isbn", "qty", "available")
        self.books_tree = ttk.Treeview(
            self.books_tab, columns=cols, show="headings", selectmode="browse"
        )
        headings = {
            "id": ("ID", 45),
            "title": ("Title", 260),
            "author": ("Author", 170),
            "isbn": ("ISBN", 120),
            "qty": ("Total", 55),
            "available": ("Available", 70),
        }
        for c, (text, width) in headings.items():
            self.books_tree.heading(c, text=text)
            self.books_tree.column(c, width=width, anchor="center" if c in ("id", "qty", "available") else "w")

        scroll = ttk.Scrollbar(self.books_tab, orient="vertical", command=self.books_tree.yview)
        self.books_tree.configure(yscrollcommand=scroll.set)
        self.books_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="left", fill="y", pady=8, padx=(0, 4))

        btns = ttk.Frame(self.books_tab)
        btns.pack(side="right", fill="y", padx=8, pady=8)
        ttk.Button(btns, text="Issue Book", command=self.issue_selected).pack(fill="x", pady=4)
        ttk.Button(btns, text="Delete Book", command=self.delete_selected).pack(fill="x", pady=4)

    def add_book(self):
        title = self.title_var.get().strip()
        author = self.author_var.get().strip()
        isbn = self.isbn_var.get().strip()
        qty_text = self.qty_var.get().strip()

        if not title or not author:
            messagebox.showwarning("Missing data", "Title and Author are required.")
            return
        if not qty_text.isdigit() or int(qty_text) < 1:
            messagebox.showwarning("Invalid quantity", "Quantity must be a positive whole number.")
            return

        try:
            self.db.add_book(title, author, isbn, int(qty_text))
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "A book with this ISBN already exists.")
            return

        self.title_var.set("")
        self.author_var.set("")
        self.isbn_var.set("")
        self.qty_var.set("1")
        self.refresh_books()

    def selected_book_id(self):
        sel = self.books_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Please select a book first.")
            return None
        return int(self.books_tree.item(sel[0])["values"][0])

    def delete_selected(self):
        book_id = self.selected_book_id()
        if book_id is None:
            return
        if self.db.active_issue_count(book_id) > 0:
            messagebox.showerror(
                "Cannot delete", "This book is currently issued. Return it first."
            )
            return
        if messagebox.askyesno("Confirm", "Delete the selected book?"):
            self.db.delete_book(book_id)
            self.refresh_books()
            self.refresh_issues()

    def issue_selected(self):
        book_id = self.selected_book_id()
        if book_id is None:
            return
        member = simpledialog.askstring("Issue Book", "Member name:", parent=self)
        if member is None:
            return
        member = member.strip()
        if not member:
            messagebox.showwarning("Missing data", "Member name cannot be empty.")
            return
        if self.db.issue_book(book_id, member):
            messagebox.showinfo(
                "Issued", f"Book issued to {member}.\nDue in {LOAN_DAYS} days."
            )
            self.refresh_books()
            self.refresh_issues()
        else:
            messagebox.showerror("Unavailable", "No copies of this book are available.")

    def refresh_books(self):
        self.books_tree.delete(*self.books_tree.get_children())
        for row in self.db.get_books(self.search_var.get().strip()):
            book_id, title, author, isbn, qty, available = row
            self.books_tree.insert(
                "", "end", values=(book_id, title, author, isbn or "", qty, available)
            )

    def build_issued_tab(self):
        cols = ("id", "title", "member", "issued", "due")
        self.issues_tree = ttk.Treeview(
            self.issued_tab, columns=cols, show="headings", selectmode="browse"
        )
        headings = {
            "id": ("Issue ID", 70),
            "title": ("Book", 280),
            "member": ("Member", 160),
            "issued": ("Issued On", 100),
            "due": ("Due Date", 100),
        }
        for c, (text, width) in headings.items():
            self.issues_tree.heading(c, text=text)
            self.issues_tree.column(c, width=width, anchor="center" if c == "id" else "w")
        self.issues_tree.tag_configure("overdue", foreground="red")

        scroll = ttk.Scrollbar(self.issued_tab, orient="vertical", command=self.issues_tree.yview)
        self.issues_tree.configure(yscrollcommand=scroll.set)
        self.issues_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll.pack(side="left", fill="y", pady=8, padx=(0, 4))

        btns = ttk.Frame(self.issued_tab)
        btns.pack(side="right", fill="y", padx=8, pady=8)
        ttk.Button(btns, text="Return Book", command=self.return_selected).pack(fill="x", pady=4)
        ttk.Label(btns, text="Red = overdue", foreground="red").pack(pady=10)

    def return_selected(self):
        sel = self.issues_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Please select an issued book first.")
            return
        issue_id = int(self.issues_tree.item(sel[0])["values"][0])
        if self.db.return_book(issue_id):
            messagebox.showinfo("Returned", "Book returned successfully.")
            self.refresh_books()
            self.refresh_issues()

    def refresh_issues(self):
        self.issues_tree.delete(*self.issues_tree.get_children())
        today = date.today().isoformat()
        for issue_id, title, member, issued, due in self.db.get_active_issues():
            tag = "overdue" if due < today else ""
            self.issues_tree.insert(
                "", "end", values=(issue_id, title, member, issued, due), tags=(tag,)
            )


if __name__ == "__main__":
    app = LibraryApp()
    app.mainloop()

