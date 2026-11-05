"""Seed realistic, reproducible demo data.

1. Static data: policies, holidays, 112 titles (+copies), 36 members, users, rules, settings.
2. ~200 days of planned circulation history (returned loans, fines, payments, waivers),
   generated with the same hidden behaviour model as the synthetic ML dataset.
3. Train the ML models (synthetic data + the library's own history).
4. A 21-day *warm-up* that runs the real agent loop once per simulated day — issuing,
   returning, reserving, paying — so notifications, cycles, outcomes and analytics are
   populated organically up to the simulated "today" (2 Nov 2026).

Run: ``python -m app.seed`` (``--reset`` to wipe and reseed).
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, db as dbm
from .models import Approval, Book, Copy, Fine, Holiday, Loan, Member, Payment, Policy, Reservation, Rule, Setting, User, Waiver
from .security import hash_password
from .services import circulation, ml, oversight
from .services import fines as fine_engine
from .services.agent import run_cycle
from .services.knowledge_base import DEFAULT_RULES
from .services.settings import DEFAULT_START_DATE, DEFAULTS, set_today

SEED = 2026
START = DEFAULT_START_DATE
WARMUP_DAYS = 21
HISTORY_DAYS = 200

POLICIES = [
    dict(member_type="student", label="Student", max_loans=4, loan_days=14, max_renewals=2, max_reservations=3, grace_days=2,
         fine_slabs=[{"from_day": 1, "to_day": 7, "rate": 2}, {"from_day": 8, "to_day": 14, "rate": 5}, {"from_day": 15, "to_day": None, "rate": 10}],
         max_fine=300, exclude_sundays=True, lost_after_days=30, lost_processing_fee=100, hold_days=3),
    dict(member_type="faculty", label="Faculty", max_loans=10, loan_days=30, max_renewals=3, max_reservations=5, grace_days=3,
         fine_slabs=[{"from_day": 1, "to_day": 7, "rate": 1}, {"from_day": 8, "to_day": 14, "rate": 2}, {"from_day": 15, "to_day": None, "rate": 5}],
         max_fine=200, exclude_sundays=True, lost_after_days=45, lost_processing_fee=100, hold_days=5),
    dict(member_type="staff", label="Staff", max_loans=5, loan_days=21, max_renewals=2, max_reservations=3, grace_days=2,
         fine_slabs=[{"from_day": 1, "to_day": 7, "rate": 2}, {"from_day": 8, "to_day": 14, "rate": 4}, {"from_day": 15, "to_day": None, "rate": 8}],
         max_fine=250, exclude_sundays=True, lost_after_days=35, lost_processing_fee=100, hold_days=4),
]

HOLIDAYS = [
    ("2026-05-01", "Labour Day"), ("2026-08-15", "Independence Day"), ("2026-08-28", "Raksha Bandhan"),
    ("2026-09-14", "Ganesh Chaturthi"), ("2026-10-02", "Gandhi Jayanti"), ("2026-10-20", "Dussehra"),
    ("2026-11-09", "Diwali (library closed)"), ("2026-11-24", "Guru Nanak Jayanti"), ("2026-12-25", "Christmas"),
    ("2027-01-01", "New Year's Day"), ("2027-01-26", "Republic Day"),
]

BOOKS: list[tuple[str, str, str, str, int]] = [
    # Computer Science
    ("Introduction to Algorithms", "Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein", "Computer Science", "MIT Press", 2022),
    ("The Algorithm Design Manual", "Steven S. Skiena", "Computer Science", "Springer", 2020),
    ("Structure and Interpretation of Computer Programs", "Harold Abelson, Gerald Jay Sussman", "Computer Science", "MIT Press", 1996),
    ("Clean Code", "Robert C. Martin", "Computer Science", "Prentice Hall", 2008),
    ("Design Patterns: Elements of Reusable Object-Oriented Software", "Erich Gamma, Richard Helm, Ralph Johnson, John Vlissides", "Computer Science", "Addison-Wesley", 1994),
    ("Computer Networks", "Andrew S. Tanenbaum, Nick Feamster, David Wetherall", "Computer Science", "Pearson", 2021),
    ("Operating System Concepts", "Abraham Silberschatz, Peter B. Galvin, Greg Gagne", "Computer Science", "Wiley", 2018),
    ("Database System Concepts", "Abraham Silberschatz, Henry F. Korth, S. Sudarshan", "Computer Science", "McGraw Hill", 2019),
    ("Computer Organization and Design", "David A. Patterson, John L. Hennessy", "Computer Science", "Morgan Kaufmann", 2020),
    ("The Pragmatic Programmer", "David Thomas, Andrew Hunt", "Computer Science", "Addison-Wesley", 2019),
    ("Compilers: Principles, Techniques, and Tools", "Alfred V. Aho, Monica S. Lam, Ravi Sethi, Jeffrey D. Ullman", "Computer Science", "Pearson", 2006),
    ("Introduction to the Theory of Computation", "Michael Sipser", "Computer Science", "Cengage", 2012),
    ("Let Us C", "Yashavant Kanetkar", "Computer Science", "BPB Publications", 2020),
    ("Head First Java", "Kathy Sierra, Bert Bates, Trisha Gee", "Computer Science", "O'Reilly", 2022),
    ("Python Crash Course", "Eric Matthes", "Computer Science", "No Starch Press", 2023),
    ("Designing Data-Intensive Applications", "Martin Kleppmann", "Computer Science", "O'Reilly", 2017),
    # Artificial Intelligence
    ("Artificial Intelligence: A Modern Approach", "Stuart Russell, Peter Norvig", "Artificial Intelligence", "Pearson", 2020),
    ("Pattern Recognition and Machine Learning", "Christopher M. Bishop", "Artificial Intelligence", "Springer", 2006),
    ("Deep Learning", "Ian Goodfellow, Yoshua Bengio, Aaron Courville", "Artificial Intelligence", "MIT Press", 2016),
    ("Hands-On Machine Learning with Scikit-Learn, Keras & TensorFlow", "Aurélien Géron", "Artificial Intelligence", "O'Reilly", 2022),
    ("Machine Learning", "Tom M. Mitchell", "Artificial Intelligence", "McGraw Hill", 1997),
    ("Artificial Intelligence", "Elaine Rich, Kevin Knight, Shivashankar B. Nair", "Artificial Intelligence", "McGraw Hill", 2017),
    ("Reinforcement Learning: An Introduction", "Richard S. Sutton, Andrew G. Barto", "Artificial Intelligence", "MIT Press", 2018),
    ("Speech and Language Processing", "Daniel Jurafsky, James H. Martin", "Artificial Intelligence", "Pearson", 2023),
    ("The Elements of Statistical Learning", "Trevor Hastie, Robert Tibshirani, Jerome Friedman", "Artificial Intelligence", "Springer", 2017),
    ("Probabilistic Graphical Models", "Daphne Koller, Nir Friedman", "Artificial Intelligence", "MIT Press", 2009),
    ("Fuzzy Logic with Engineering Applications", "Timothy J. Ross", "Artificial Intelligence", "Wiley", 2016),
    ("Expert Systems: Principles and Programming", "Joseph C. Giarratano, Gary D. Riley", "Artificial Intelligence", "Cengage", 2004),
    ("Human Compatible", "Stuart Russell", "Artificial Intelligence", "Penguin", 2019),
    ("Life 3.0", "Max Tegmark", "Artificial Intelligence", "Penguin", 2017),
    # Mathematics
    ("Higher Engineering Mathematics", "B. S. Grewal", "Mathematics", "Khanna Publishers", 2020),
    ("Advanced Engineering Mathematics", "Erwin Kreyszig", "Mathematics", "Wiley", 2011),
    ("Linear Algebra and Its Applications", "Gilbert Strang", "Mathematics", "Cengage", 2005),
    ("Discrete Mathematics and Its Applications", "Kenneth H. Rosen", "Mathematics", "McGraw Hill", 2018),
    ("Calculus: Early Transcendentals", "James Stewart", "Mathematics", "Cengage", 2015),
    ("Introduction to Probability", "Joseph K. Blitzstein, Jessica Hwang", "Mathematics", "CRC Press", 2019),
    ("Concrete Mathematics", "Ronald L. Graham, Donald E. Knuth, Oren Patashnik", "Mathematics", "Addison-Wesley", 1994),
    ("Mathematics for Machine Learning", "Marc Peter Deisenroth, A. Aldo Faisal, Cheng Soon Ong", "Mathematics", "Cambridge University Press", 2020),
    ("Probability and Statistics for Engineers and Scientists", "Ronald E. Walpole, Raymond H. Myers", "Mathematics", "Pearson", 2016),
    ("Numerical Methods for Engineers", "Steven C. Chapra, Raymond P. Canale", "Mathematics", "McGraw Hill", 2020),
    # Physics
    ("Concepts of Physics, Vol. 1", "H. C. Verma", "Physics", "Bharati Bhawan", 2019),
    ("Fundamentals of Physics", "David Halliday, Robert Resnick, Jearl Walker", "Physics", "Wiley", 2018),
    ("The Feynman Lectures on Physics, Vol. 1", "Richard P. Feynman, Robert B. Leighton, Matthew Sands", "Physics", "Basic Books", 2011),
    ("Introduction to Electrodynamics", "David J. Griffiths", "Physics", "Cambridge University Press", 2017),
    ("Introduction to Quantum Mechanics", "David J. Griffiths, Darrell F. Schroeter", "Physics", "Cambridge University Press", 2018),
    ("A Brief History of Time", "Stephen Hawking", "Physics", "Bantam", 1998),
    ("Engineering Physics", "R. K. Gaur, S. L. Gupta", "Physics", "Dhanpat Rai Publications", 2015),
    ("University Physics", "Hugh D. Young, Roger A. Freedman", "Physics", "Pearson", 2019),
    # Electronics
    ("Electronic Devices and Circuit Theory", "Robert L. Boylestad, Louis Nashelsky", "Electronics", "Pearson", 2015),
    ("Microelectronic Circuits", "Adel S. Sedra, Kenneth C. Smith", "Electronics", "Oxford University Press", 2019),
    ("Digital Design", "M. Morris Mano, Michael D. Ciletti", "Electronics", "Pearson", 2018),
    ("Signals and Systems", "Alan V. Oppenheim, Alan S. Willsky", "Electronics", "Pearson", 2015),
    ("The Art of Electronics", "Paul Horowitz, Winfield Hill", "Electronics", "Cambridge University Press", 2015),
    ("Communication Systems", "Simon Haykin, Michael Moher", "Electronics", "Wiley", 2009),
    ("Microprocessor Architecture, Programming and Applications with the 8085", "Ramesh S. Gaonkar", "Electronics", "Penram", 2013),
    ("Control Systems Engineering", "Norman S. Nise", "Electronics", "Wiley", 2019),
    # Mechanical Engineering
    ("Engineering Mechanics: Statics", "J. L. Meriam, L. G. Kraige", "Mechanical Engineering", "Wiley", 2016),
    ("Thermodynamics: An Engineering Approach", "Yunus A. Çengel, Michael A. Boles", "Mechanical Engineering", "McGraw Hill", 2019),
    ("Theory of Machines", "S. S. Rattan", "Mechanical Engineering", "McGraw Hill", 2019),
    ("Strength of Materials", "R. K. Bansal", "Mechanical Engineering", "Laxmi Publications", 2018),
    ("Fluid Mechanics", "Frank M. White", "Mechanical Engineering", "McGraw Hill", 2016),
    ("Shigley's Mechanical Engineering Design", "Richard G. Budynas, J. Keith Nisbett", "Mechanical Engineering", "McGraw Hill", 2020),
    ("Manufacturing Engineering and Technology", "Serope Kalpakjian, Steven R. Schmid", "Mechanical Engineering", "Pearson", 2014),
    # Literature
    ("Pride and Prejudice", "Jane Austen", "Literature", "Penguin Classics", 2003),
    ("To Kill a Mockingbird", "Harper Lee", "Literature", "Harper Perennial", 2006),
    ("One Hundred Years of Solitude", "Gabriel García Márquez", "Literature", "Harper Perennial", 2006),
    ("The God of Small Things", "Arundhati Roy", "Literature", "Penguin India", 2002),
    ("Midnight's Children", "Salman Rushdie", "Literature", "Vintage", 2006),
    ("Nineteen Eighty-Four", "George Orwell", "Literature", "Penguin", 2008),
    ("The Guide", "R. K. Narayan", "Literature", "Indian Thought Publications", 2010),
    ("Gitanjali", "Rabindranath Tagore", "Literature", "Macmillan", 2011),
    ("The White Tiger", "Aravind Adiga", "Literature", "HarperCollins", 2008),
    ("Things Fall Apart", "Chinua Achebe", "Literature", "Penguin", 2006),
    ("The Great Gatsby", "F. Scott Fitzgerald", "Literature", "Scribner", 2004),
    ("Frankenstein", "Mary Shelley", "Literature", "Penguin Classics", 2003),
    # History
    ("The Discovery of India", "Jawaharlal Nehru", "History", "Penguin India", 2008),
    ("India After Gandhi", "Ramachandra Guha", "History", "Picador", 2017),
    ("Sapiens: A Brief History of Humankind", "Yuval Noah Harari", "History", "Harper", 2015),
    ("Guns, Germs, and Steel", "Jared Diamond", "History", "W. W. Norton", 2017),
    ("The Wonder That Was India", "A. L. Basham", "History", "Picador", 2004),
    ("An Era of Darkness", "Shashi Tharoor", "History", "Aleph", 2016),
    ("The Silk Roads", "Peter Frankopan", "History", "Bloomsbury", 2016),
    ("India's Struggle for Independence", "Bipan Chandra", "History", "Penguin India", 2016),
    # Economics
    ("Principles of Economics", "N. Gregory Mankiw", "Economics", "Cengage", 2020),
    ("Thinking, Fast and Slow", "Daniel Kahneman", "Economics", "Farrar, Straus and Giroux", 2011),
    ("Capital in the Twenty-First Century", "Thomas Piketty", "Economics", "Harvard University Press", 2014),
    ("Poor Economics", "Abhijit V. Banerjee, Esther Duflo", "Economics", "PublicAffairs", 2011),
    ("Freakonomics", "Steven D. Levitt, Stephen J. Dubner", "Economics", "William Morrow", 2009),
    ("Indian Economy", "Ramesh Singh", "Economics", "McGraw Hill", 2022),
    ("The Wealth of Nations", "Adam Smith", "Economics", "Penguin Classics", 1982),
    ("Nudge: The Final Edition", "Richard H. Thaler, Cass R. Sunstein", "Economics", "Penguin", 2021),
    # Management
    ("The Lean Startup", "Eric Ries", "Management", "Crown Business", 2011),
    ("Good to Great", "Jim Collins", "Management", "HarperBusiness", 2001),
    ("Principles of Marketing", "Philip Kotler, Gary Armstrong", "Management", "Pearson", 2020),
    ("The Effective Executive", "Peter F. Drucker", "Management", "Harper Business", 2006),
    ("Zero to One", "Peter Thiel, Blake Masters", "Management", "Crown Business", 2014),
    ("Atomic Habits", "James Clear", "Management", "Avery", 2018),
    ("Organizational Behavior", "Stephen P. Robbins, Timothy A. Judge", "Management", "Pearson", 2019),
    ("The Innovator's Dilemma", "Clayton M. Christensen", "Management", "Harvard Business Review Press", 2016),
    # Biology
    ("Campbell Biology", "Lisa A. Urry, Michael L. Cain, Steven A. Wasserman", "Biology", "Pearson", 2020),
    ("The Selfish Gene", "Richard Dawkins", "Biology", "Oxford University Press", 2016),
    ("Molecular Biology of the Cell", "Bruce Alberts, Alexander Johnson, Julian Lewis", "Biology", "Garland Science", 2014),
    ("The Gene: An Intimate History", "Siddhartha Mukherjee", "Biology", "Scribner", 2016),
    ("The Emperor of All Maladies", "Siddhartha Mukherjee", "Biology", "Scribner", 2010),
    ("Lehninger Principles of Biochemistry", "David L. Nelson, Michael M. Cox", "Biology", "W. H. Freeman", 2017),
    # Philosophy
    ("The Republic", "Plato (trans. Desmond Lee)", "Philosophy", "Penguin Classics", 2007),
    ("Meditations", "Marcus Aurelius (trans. Martin Hammond)", "Philosophy", "Penguin Classics", 2006),
    ("Sophie's World", "Jostein Gaarder", "Philosophy", "Farrar, Straus and Giroux", 2007),
    ("The Bhagavad Gita", "Eknath Easwaran (trans.)", "Philosophy", "Nilgiri Press", 2007),
    ("Thus Spoke Zarathustra", "Friedrich Nietzsche", "Philosophy", "Penguin Classics", 1961),
    ("Gödel, Escher, Bach", "Douglas R. Hofstadter", "Philosophy", "Basic Books", 1999),
    ("The Myth of Sisyphus", "Albert Camus", "Philosophy", "Vintage", 1991),
]

DEMO_TITLE = "Artificial Intelligence: A Modern Approach"

# (name, type, department, notify_pref, hidden_habit or None)
MEMBERS: list[tuple[str, str, str, str, float | None]] = [
    ("Aarav Sharma", "student", "Computer Science & Engg.", "sms", 0.42),
    ("Riya Patel", "student", "Computer Science & Engg.", "email", 0.15),
    ("Kabir Singh", "student", "Electronics & Communication", "in_app", 0.30),
    ("Ananya Reddy", "student", "Computer Science & Engg.", "email", None),
    ("Vihaan Gupta", "student", "Mechanical Engg.", "sms", None),
    ("Ishita Nair", "student", "AI & Data Science", "email", None),
    ("Arjun Menon", "student", "Electrical & Electronics", "in_app", None),
    ("Diya Kapoor", "student", "AI & Data Science", "email", None),
    ("Rohan Das", "student", "Computer Science & Engg.", "sms", 0.62),
    ("Sneha Kulkarni", "student", "Civil Engg.", "email", None),
    ("Aditya Verma", "student", "Mechanical Engg.", "in_app", 0.55),
    ("Kavya Joshi", "student", "Computer Science & Engg.", "email", None),
    ("Siddharth Rao", "student", "Electronics & Communication", "sms", None),
    ("Meghna Banerjee", "student", "AI & Data Science", "email", 0.08),
    ("Nikhil Chauhan", "student", "Information Technology", "sms", 0.58),
    ("Pooja Iyer", "student", "Information Technology", "email", None),
    ("Harsh Agarwal", "student", "Computer Science & Engg.", "in_app", None),
    ("Tanvi Mishra", "student", "Biotechnology", "email", None),
    ("Yash Thakur", "student", "Mechanical Engg.", "sms", 0.50),
    ("Aisha Khan", "student", "Computer Science & Engg.", "email", None),
    ("Rahul Pillai", "student", "Electrical & Electronics", "in_app", None),
    ("Neha Saxena", "student", "Biotechnology", "email", 0.10),
    ("Manav Bhatt", "student", "Information Technology", "sms", None),
    ("Zoya Ahmed", "student", "AI & Data Science", "email", None),
    ("Dr. Meera Iyer", "faculty", "Computer Science & Engg.", "email", 0.12),
    ("Prof. Rajesh Kumar", "faculty", "Electronics & Communication", "email", None),
    ("Dr. Sunita Rao", "faculty", "Mathematics", "in_app", None),
    ("Dr. Vikram Sethi", "faculty", "Mechanical Engg.", "sms", 0.40),
    ("Prof. Lakshmi Narayanan", "faculty", "Physics", "email", None),
    ("Dr. Farhan Qureshi", "faculty", "Management Studies", "email", None),
    ("Dr. Priya Deshmukh", "faculty", "AI & Data Science", "in_app", None),
    ("Prof. Anil Bhattacharya", "faculty", "Humanities", "email", None),
    ("Suresh Yadav", "staff", "Administration", "sms", None),
    ("Kavitha Krishnan", "staff", "Accounts", "email", None),
    ("Deepak Joshi", "staff", "Laboratory Services", "in_app", 0.45),
    ("Fatima Sheikh", "staff", "Placement Cell", "email", None),
]
CAST_LIMITED = {"Aarav Sharma": 2, "Dr. Meera Iyer": 4, "Riya Patel": 2, "Kabir Singh": 2}

DEMO_USERS = [
    ("admin@library.local", "Admin@123", "Dr. Kalpana Rao", "admin"),
    ("librarian@library.local", "Librarian@123", "Ramesh Pai", "librarian"),
    ("member@library.local", "Member@123", None, "member"),  # linked to Aarav Sharma
]


def isbn13(rng: random.Random) -> str:
    digits = [9, 7, 8, 9, 3] + [rng.randint(0, 9) for _ in range(7)]
    check = (10 - sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10) % 10
    return "".join(map(str, digits + [check]))


def _email(name: str) -> str:
    parts = name.replace("Dr. ", "").replace("Prof. ", "").lower().split()
    return f"{parts[0]}.{parts[-1]}@college.edu"


@dataclass
class MemberSim:
    member: Member
    habit: float
    weight: float
    max_loans: int
    intervals: list[tuple[date, date | None]] = field(default_factory=list)
    history: list[tuple[date, bool]] = field(default_factory=list)
    fines: list[tuple[date, date | None, float]] = field(default_factory=list)

    def active_at(self, d: date) -> int:
        return sum(1 for s, e in self.intervals if s <= d and (e is None or e > d))

    def stats_at(self, d: date) -> tuple[int, float, float]:
        prior = [late for ret, late in self.history if ret < d]
        unpaid = sum(a for c, p, a in self.fines if c <= d and (p is None or p > d))
        return len(prior), (round(sum(prior) / len(prior), 3) if prior else 0.0), round(unpaid, 2)


def _create_static(db: Session, rng: random.Random) -> dict[str, Any]:
    for p in POLICIES:
        db.add(Policy(**p))
    for d, name in HOLIDAYS:
        db.add(Holiday(date=date.fromisoformat(d), name=name))
    for key, value in DEFAULTS.items():
        db.add(Setting(key=key, value=value))
    for r in DEFAULT_RULES:
        db.add(Rule(**r))

    books: list[Book] = []
    shelf_codes = {c: f"{c[:2].upper()}" for c in ml.CATEGORIES}
    copy_no = 1
    for i, (title, author, cat, pub, year) in enumerate(BOOKS):
        price = float(rng.choice([350, 450, 499, 599, 650, 750, 899, 950, 1095, 1250, 1450]))
        book = Book(
            isbn=isbn13(rng), title=title, author=author, category=cat, publisher=pub, year=year, price=price,
            description=f"{title} by {author} ({pub}, {year}). Part of the {cat} collection.",
        )
        db.add(book)
        db.flush()
        if title == DEMO_TITLE:
            db.add(Copy(book_id=book.id, barcode="DEMO-AIMA-01", status="available", shelf=f"{shelf_codes[cat]}-R1", acquired_on=date(2024, 6, 1)))
        else:
            n = rng.choices([1, 2, 3, 4], weights=[3, 4, 2, 1])[0]
            for _ in range(n):
                db.add(Copy(book_id=book.id, barcode=f"LIB-{copy_no:05d}", status="available",
                            shelf=f"{shelf_codes[cat]}-{rng.randint(1, 9)}{rng.choice('ABCD')}",
                            acquired_on=date(rng.randint(2015, 2025), rng.randint(1, 12), rng.randint(1, 28))))
                copy_no += 1
        books.append(book)

    member_sims: dict[int, MemberSim] = {}
    counters = {"student": 2024001, "faculty": 1001, "staff": 501}
    prefix = {"student": "S", "faculty": "F", "staff": "T"}
    policies = {p["member_type"]: p for p in POLICIES}
    for name, mtype, dept, pref, habit in MEMBERS:
        code = f"{prefix[mtype]}{counters[mtype]}"
        counters[mtype] += 1
        m = Member(code=code, name=name, email=_email(name), phone=f"+91 9{rng.randint(100000000, 999999999)}", member_type=mtype,
                   department=dept, joined_on=date(rng.randint(2019, 2025), rng.randint(1, 12), rng.randint(1, 28)), status="active", notify_pref=pref)
        db.add(m)
        db.flush()
        h = habit if habit is not None else rng.betavariate(2.0, 5.5) * (1.15 if mtype == "student" else 0.8)
        weight = {"student": 1.0, "faculty": 0.8, "staff": 0.5}[mtype] * (1.6 if name == "Aarav Sharma" else 1.0)
        member_sims[m.id] = MemberSim(m, round(min(h, 0.9), 3), weight, CAST_LIMITED.get(name, policies[mtype]["max_loans"]))

    # users
    pw_member = "Member@123"
    aarav = next(ms.member for ms in member_sims.values() if ms.member.name == "Aarav Sharma")
    for email, pw, name, role in DEMO_USERS:
        if role == "member":
            db.add(User(email=email, name=aarav.name, password_hash=hash_password(pw), role=role, member_id=aarav.id))
        else:
            db.add(User(email=email, name=name, password_hash=hash_password(pw), role=role))
    db.add(User(email="asha.librarian@library.local", name="Asha Fernandes", password_hash=hash_password("Librarian@123"), role="librarian"))
    for ms in member_sims.values():
        if ms.member.id == aarav.id:
            continue
        db.add(User(email=ms.member.email, name=ms.member.name, password_hash=hash_password(pw_member), role="member", member_id=ms.member.id))
    db.flush()
    return {"books": books, "members": member_sims}


def _plan_return(rng: random.Random, feats: dict[str, Any], habit: float, issued: date, due: date) -> date:
    p = ml.latent_late_probability(feats, habit)
    if rng.random() < p:
        late = min(1 + int(rng.expovariate(1 / 6.0)), 75)
        return due + timedelta(days=late)
    span = max((due - issued).days, 3)
    return issued + timedelta(days=rng.randint(2, span))


def _generate_history(db: Session, rng: random.Random, static: dict[str, Any], warm_start: date) -> dict[int, date | None]:
    books: list[Book] = static["books"]
    sims: dict[int, MemberSim] = static["members"]
    policies = {p.member_type: p for p in db.scalars(select(Policy))}
    holidays = circulation.holiday_dates(db)
    weights = []
    for b in books:
        base = {"Artificial Intelligence": 2.2, "Computer Science": 2.0, "Mathematics": 1.6, "Electronics": 1.2, "Physics": 1.2}.get(b.category, 0.8)
        weights.append(base * rng.uniform(0.4, 1.6))
    copies_by_book: dict[int, list[Copy]] = {}
    for c in db.scalars(select(Copy)):
        if not c.barcode.startswith("DEMO"):
            copies_by_book.setdefault(c.book_id, []).append(c)
    free_from: dict[int, date] = {c.id: date.min for cs in copies_by_book.values() for c in cs}
    member_list = list(sims.values())
    m_weights = [ms.weight for ms in member_list]
    stuck = 0

    planned: list[dict[str, Any]] = []
    d = warm_start - timedelta(days=HISTORY_DAYS)
    while d < warm_start:
        if d in holidays or d.weekday() == 6:
            d += timedelta(days=1)
            continue
        n = rng.choices([3, 4, 5, 6, 7], weights=[2, 3, 4, 3, 1])[0] + (1 if d.month in (4, 10, 11) else 0)
        for _ in range(n):
            ms = rng.choices(member_list, weights=m_weights)[0]
            if ms.active_at(d) >= ms.max_loans:
                continue
            book = rng.choices(books, weights=weights)[0]
            free = [c for c in copies_by_book.get(book.id, []) if free_from[c.id] <= d]
            if not free:
                continue
            copy = free[0]
            policy = policies[ms.member.member_type]
            due = circulation.next_open_day(d + timedelta(days=policy.loan_days), holidays, policy.exclude_sundays)
            prior, late_rate, unpaid = ms.stats_at(d)
            feats = {
                "prior_loans": prior, "prior_late_rate": late_rate, "unpaid_fines": unpaid, "active_loans": ms.active_at(d),
                "title_demand": rng.choices([0, 0, 0, 1, 2], k=1)[0], "loan_days": policy.loan_days,
                "exam_period": ml.is_exam_period(d), "weekend_checkout": int(d.weekday() >= 5),
                "member_type": ms.member.member_type, "category": book.category,
            }
            ret: date | None = _plan_return(rng, feats, ms.habit, d, due)
            if stuck < 6 and warm_start - timedelta(days=48) <= d <= warm_start - timedelta(days=22) and ms.habit > 0.35 and rng.random() < 0.25:
                ret = None  # never returned → becomes a lost-book candidate
                stuck += 1
            free_from[copy.id] = (ret + timedelta(days=1)) if ret else date.max
            ms.intervals.append((d, ret))
            if ret is not None and ret < warm_start:
                late = ret > due
                ms.history.append((ret, late))
                if late:
                    pol = circulation.fine_policy(policy)
                    amount = fine_engine.compute_overdue_fine(due, ret, pol, holidays).total
                    if amount > 0:
                        pay = ret + timedelta(days=rng.randint(0, 25)) if rng.random() > ms.habit * 0.7 else None
                        ms.fines.append((ret, pay, amount))
            planned.append({"ms": ms, "copy": copy, "issued": d, "due": due, "ret": ret, "feats": feats})
        d += timedelta(days=1)

    planned_returns: dict[int, date | None] = {}
    librarian = db.scalar(select(User).where(User.email == "librarian@library.local"))
    for p in planned:
        ms: MemberSim = p["ms"]
        ret: date | None = p["ret"]
        returned = ret is not None and ret < warm_start
        loan = Loan(copy_id=p["copy"].id, member_id=ms.member.id, issued_on=p["issued"], due_on=p["due"],
                    returned_on=ret if returned else None, status="returned" if returned else "active",
                    issued_by=librarian.id if librarian else None, risk_detail={"features": p["feats"]})
        if returned and ret and ret <= p["due"] and (p["due"] - p["issued"]).days >= 14 and rng.random() < 0.12:
            loan.renewals = 1
        db.add(loan)
        db.flush()
        if not returned:
            p["copy"].status = "on_loan"
            planned_returns[loan.id] = ret
            continue
        if ret and ret > p["due"]:
            loan.member = ms.member
            fine = circulation.refresh_fine(db, loan, holidays, on=ret)
            if fine is None:
                continue
            fine.created_on = ret
            match = next((f for f in ms.fines if f[0] == ret and abs(f[2] - fine.amount) < 0.01), None)
            pay_date = match[1] if match else None
            roll = rng.random()
            if roll < 0.06:
                db.add(Waiver(fine_id=fine.id, amount=fine.amount, reason=rng.choice([
                    "Medical certificate submitted for the delay", "Library closed unexpectedly during the due week",
                    "First delay in three years — goodwill waiver", "Book was returned to the drop box before due date"]),
                    approved_by=librarian.id if librarian else None, waived_on=ret + timedelta(days=1)))
                fine.amount_waived = fine.amount
            elif pay_date is not None and pay_date < warm_start:
                amount = fine.amount if rng.random() < 0.82 else round(fine.amount / 2, 2)
                db.add(Payment(fine_id=fine.id, amount=amount, method=rng.choice(["cash", "upi", "upi", "card"]),
                               paid_on=pay_date, recorded_by=librarian.id if librarian else None))
                fine.amount_paid = amount
            fine.status = fine_engine.fine_status(fine.amount, fine.amount_paid, fine.amount_waived, False)
    db.flush()
    return planned_returns


def _predict_active(db: Session) -> None:
    for loan in db.scalars(select(Loan).where(Loan.status == "active")):
        feats = (loan.risk_detail or {}).get("features")
        if not feats:
            continue
        pred = ml.predict(db, feats)
        if pred:
            loan.risk_score, loan.risk_label = pred["probability"], pred["label"]
            loan.risk_detail = pred | {"features": feats}


def _warmup(db: Session, rng: random.Random, static: dict[str, Any], planned_returns: dict[int, date | None], warm_start: date) -> None:
    sims: dict[int, MemberSim] = static["members"]
    librarian = db.scalar(select(User).where(User.email == "librarian@library.local"))
    assert librarian is not None
    book_weights = {b.id: ({"Artificial Intelligence": 2.2, "Computer Science": 2.0, "Mathematics": 1.6}.get(b.category, 0.9)) for b in static["books"]}
    cast_names = set(CAST_LIMITED)
    d = warm_start
    while d < START:
        d += timedelta(days=1)
        set_today(db, d)
        db.flush()
        closed = d in circulation.holiday_dates(db) or d.weekday() == 6
        # planned returns
        for loan_id, ret in list(planned_returns.items()):
            if ret == d and not closed:
                loan = db.get(Loan, loan_id)
                if loan and loan.status == "active":
                    circulation.return_loan(db, loan_id, librarian, label="Circulation desk")
                planned_returns.pop(loan_id)
            elif ret is not None and ret < d and closed is False:
                loan = db.get(Loan, loan_id)
                if loan and loan.status == "active":
                    circulation.return_loan(db, loan_id, librarian, label="Circulation desk")
                planned_returns.pop(loan_id)
        if not closed:
            # members collect holds
            for res in db.scalars(select(Reservation).where(Reservation.status == "ready")).all():
                if rng.random() < 0.55:
                    try:
                        with db.begin_nested():
                            loan = circulation.issue(db, res.member_id, librarian, book_id=res.book_id, label="Circulation desk")
                        _plan(db, rng, loan, sims, planned_returns)
                    except circulation.DomainError:
                        pass
            # new checkouts
            available = db.scalars(select(Copy).where(Copy.status == "available", ~Copy.barcode.startswith("DEMO"))).all()
            members = [ms for ms in sims.values() if ms.member.status == "active"]
            for _ in range(rng.choice([4, 5, 6, 7])):
                if not available:
                    break
                ms = rng.choices(members, weights=[m.weight for m in members])[0]
                copy = rng.choices(available, weights=[book_weights.get(c.book_id, 1.0) for c in available])[0]
                if ms.member.name in CAST_LIMITED:
                    active = db.scalar(select(func.count(Loan.id)).where(Loan.member_id == ms.member.id, Loan.status == "active")) or 0
                    if active >= CAST_LIMITED[ms.member.name]:
                        continue
                try:
                    with db.begin_nested():
                        loan = circulation.issue(db, ms.member.id, librarian, copy_id=copy.id, label="Circulation desk")
                    _plan(db, rng, loan, sims, planned_returns)
                    available.remove(copy)
                except circulation.DomainError:
                    pass
            # reservations on books with no free copy
            busy_books = db.scalars(
                select(Copy.book_id).where(~Copy.barcode.startswith("DEMO")).group_by(Copy.book_id)
                .having(func.sum(Copy.status == "available") == 0)
            ).all()
            for _ in range(rng.choice([0, 1, 1, 2])):
                if not busy_books:
                    break
                ms = rng.choice([m for m in members if m.member.name not in cast_names])
                try:
                    with db.begin_nested():
                        circulation.reserve(db, ms.member.id, rng.choice(busy_books), librarian)
                except circulation.DomainError:
                    pass
            # payments
            for fine in db.scalars(select(Fine).where(Fine.status.in_(("open", "partially_paid")))).all():
                habit = sims[fine.member_id].habit
                if rng.random() < 0.18 * (1 - habit):
                    amount = fine.balance if rng.random() < 0.75 else round(fine.balance / 2, 2)
                    if amount > 0:
                        circulation.record_payment(db, fine.id, amount, rng.choice(["cash", "upi", "card"]), librarian)
            # librarian reviews some agent recommendations (older than 2 days)
            for appr in db.scalars(select(Approval).where(Approval.status == "pending", Approval.created_on <= d - timedelta(days=2))).all():
                if rng.random() < 0.5:
                    continue
                try:
                    with db.begin_nested():
                        if appr.kind == "waiver":
                            ok = rng.random() < 0.7
                            note = "Reviewed member record — goodwill waiver agreed" if ok else "Member has been reminded; fine stands"
                            oversight.decide(db, appr.id, ok, note, librarian)
                        elif appr.kind == "restrict_member":
                            oversight.decide(db, appr.id, False, "Spoke to the member; they promised to clear dues this week", librarian)
                except circulation.DomainError:
                    oversight.decide(db, appr.id, False, "Fine already settled before review", librarian)
        run_cycle(db, "seed")
        db.flush()


def _plan(db: Session, rng: random.Random, loan: Loan, sims: dict[int, MemberSim], planned: dict[int, date | None]) -> None:
    feats = (loan.risk_detail or {}).get("features")
    ret = _plan_return(rng, feats, sims[loan.member_id].habit, loan.issued_on, loan.due_on) if feats else loan.due_on
    planned[loan.id] = ret if ret < START + timedelta(days=60) else None


def _final_touches(db: Session, rng: random.Random, static: dict[str, Any]) -> None:
    """Guarantee a few live scenarios for the first manual agent cycle."""
    librarian = db.scalar(select(User).where(User.email == "librarian@library.local"))
    on = START
    # Keep the demo borrower's account tidy (no overdue loans that would compete for his daily notification limit).
    aarav = db.scalar(select(Member).where(Member.name == "Aarav Sharma"))
    for loan in db.scalars(select(Loan).where(Loan.member_id == aarav.id, Loan.status == "active")).all():
        if loan.due_on <= on + timedelta(days=4):
            circulation.return_loan(db, loan.id, librarian, label="Circulation desk")
    overdue = db.scalars(select(Loan).where(Loan.status == "active", Loan.due_on < on).order_by(Loan.due_on)).all()
    sims: dict[int, MemberSim] = static["members"]
    candidates = [ms.member for ms in sims.values() if ms.member.name not in CAST_LIMITED and ms.member.status == "active"]
    made = 0
    for loan in overdue:
        book_id = loan.copy.book_id
        if loan.copy.barcode.startswith("DEMO") or circulation.waiting_count(db, book_id) > 0:
            continue
        if db.scalar(select(func.count(Copy.id)).where(Copy.book_id == book_id, Copy.status == "available")):
            continue
        for member in rng.sample(candidates, k=len(candidates)):
            if member.id == loan.member_id:
                continue
            try:
                with db.begin_nested():
                    circulation.reserve(db, member.id, book_id, librarian)
                made += 1
                break
            except circulation.DomainError:
                continue
        if made >= 5:
            break


def seed_all(db: Session, verbose: bool = True) -> None:
    rng = random.Random(SEED)
    warm_start = START - timedelta(days=WARMUP_DAYS)
    log = (lambda msg: print(f"  • {msg}", flush=True)) if verbose else (lambda msg: None)
    log("static data (policies, holidays, 112 titles, copies, 36 members, users, rules)")
    static = _create_static(db, rng)
    set_today(db, warm_start)
    db.flush()
    log(f"circulation history {warm_start - timedelta(days=HISTORY_DAYS)} → {warm_start}")
    planned = _generate_history(db, rng, static, warm_start)
    log("training ML models (synthetic dataset + library history)")
    ml.train_and_compare(db, n_samples=4000, seed=42, include_history=True)
    _predict_active(db)
    db.commit()
    log(f"warm-up: running the agent once per simulated day {warm_start + timedelta(days=1)} → {START}")
    _warmup(db, rng, static, planned, warm_start)
    _final_touches(db, rng, static)
    set_today(db, START)
    db.commit()
    log("done")


def reset_database(verbose: bool = False) -> None:
    """Wipe and re-seed. The warm-up's agent activity is kept out of the live console log."""
    previous = os.environ.get("LIBRARY_CONSOLE_LOG")
    os.environ["LIBRARY_CONSOLE_LOG"] = "0"
    try:
        _reset_database(verbose)
    finally:
        if previous is None:
            os.environ.pop("LIBRARY_CONSOLE_LOG", None)
        else:
            os.environ["LIBRARY_CONSOLE_LOG"] = previous


def _reset_database(verbose: bool) -> None:
    dbm.drop_all()
    if config.MODELS_DIR.exists():
        shutil.rmtree(config.MODELS_DIR)
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ml._CACHE.clear()
    dbm.create_all()
    with dbm.SessionLocal() as db:
        seed_all(db, verbose=verbose)


def ensure_seeded() -> bool:
    dbm.create_all()
    with dbm.SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            return False
    reset_database(verbose=True)
    return True


def _safe_console() -> None:
    """Never crash on Windows consoles that are not UTF-8 (e.g. cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _safe_console()
    parser = argparse.ArgumentParser(description="Seed the library agent database")
    parser.add_argument("--reset", action="store_true", help="drop all data and reseed")
    args = parser.parse_args()
    if args.reset:
        print("Resetting and seeding the database…")
        reset_database(verbose=True)
    elif ensure_seeded():
        print("Database seeded.")
    else:
        print("Database already contains data (use --reset to reseed).")
    sys.exit(0)


if __name__ == "__main__":
    main()
