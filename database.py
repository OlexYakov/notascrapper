import sqlite3
from sqlite3 import Connection, Error

create_table_SQL = """
CREATE TABLE students (
	num	 BIGINT,
	name VARCHAR(512),
	PRIMARY KEY(num)
);

CREATE TABLE subjects (
	id	 BIGINT,
	name VARCHAR(512),
    sname VARCHAR(6),
	PRIMARY KEY(id)
);

CREATE TABLE grades (
	val	 SMALLINT,
	note	 VARCHAR(512),
	phase	 VARCHAR(2),
	subject_id	 BIGINT,
	student_num BIGINT,
    year year,
	PRIMARY KEY(phase,year,subject_id,student_num),
	FOREIGN KEY (subject_id) REFERENCES Subjects(id),
	FOREIGN KEY (student_num) REFERENCES Students(num)
);
"""


def create_conn(path="sqlite.db"):
    conn = None
    try:
        conn = sqlite3.connect(path)
    except Error as e:
        print(e)
    return conn


def create_table(conn: Connection, create_table_sql):
    try:
        c = conn.cursor()
        c.executescript(create_table_sql)
    except Error as e:
        print(e)


def init_database():
    conn = create_conn()
    if conn is not None:
        try:
            create_table(conn, create_table_SQL)
        except Error as e:
            print(e)
        finally:
            conn.close()


def gen_subject_snames():
    conn = create_conn()
    if conn is not None:
        subjects = conn.execute("SELECT * FROM subjects").fetchall()
        for sub in subjects:
            name = sub[1]
            sname = "".join([n for n in name if n.isupper()])
            conn.execute(
                "UPDATE subjects SET sname=? WHERE id=?", (sname, sub[0]))
        # weird cases
        queries = """
        UPDATE subjects SET sname="IARC" WHERE id=1000120;
        UPDATE subjects SET sname="PDGI" WHERE id=1000259;
        UPDATE subjects SET sname="COMP" WHERE id=1000287;
        UPDATE subjects SET sname="ESTA" WHERE id=1000079;
        UPDATE subjects SET sname="MULT" WHERE id=1000175;
        UPDATE subjects SET sname="ALGA" WHERE id=1000021;
        """
        conn.executescript(queries)
        conn.commit()
        conn.close()
