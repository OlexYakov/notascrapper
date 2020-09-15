import configparser
from configparser import ConfigParser
from typing import Dict, Mapping, Tuple
from bs4 import BeautifulSoup
import os
from types import __dict__
import re
from tinydb import TinyDB, Query, where
from threading import Thread
import sqlite3
from sqlite3 import Error
import database

pautas_root = "/home/hobocrow/repos/notas_scrapper/pautas/"

# TinyDB
db = TinyDB("db.json")
students_db = db.table("students")
grades_db = db.table("grades")

# SQLite
sqliteDb = sqlite3.connect("sqlite.db")

new_students = set()
new_courses = set()
new_grades = set()
scores = {}

config = None


def course_info_from_path(path: str) -> Tuple[str, str, str]:
    id = re.search("\(\d+\)", path)[0][1:-1]
    name = re.split("[./]", path)[-2].split("(")[0].strip()
    year = path.split("/")[-2]
    return (id, name, year)


def parse_table_row(tr: BeautifulSoup) -> Tuple[str, int, int, str]:
    name, num, _, result = [t.text.strip() for t in tr.find_all("td")]
    pattern = re.compile('\s+')
    name = pattern.sub(" ", name)
    name = name.replace("\t", "").replace("\n", "")

    grade = 0
    note = None
    if result.isnumeric():
        grade = eval(result)
    else:
        note = result

    return (name, num, grade, note)


def extract(path: str):
    course_id, course_name, year = course_info_from_path(path)
    print(f"Extracting {course_name}")

    new_courses.add((course_id, course_name))

    with open(path) as f:
        page = BeautifulSoup(f.read(), 'html.parser')
    for phase in ["EF", "EN", "ER", "EEPlus"]:
        print(f"\tPhase: {phase}")
        try:
            tbody = page.find(
                id="div_"+phase).find("table").find("table").find("tbody")
            trs = tbody.find_all("tr")
        except AttributeError:
            print(f"No valid data in {phase}, skiping")
            continue

        for tr in trs:
            name, num, grade, note = parse_table_row(tr)

            new_students.add((num, name))
            # value,note,phase,subject_id,student_num
            new_grades.add((grade, note, phase, course_id, num, year))


def start_extraction():
    year_folders = os.listdir(pautas_root)
    for fd in year_folders:
        files = os.listdir(pautas_root+fd)
        for file in files:
            extract(pautas_root+fd+"/"+file)


if __name__ == "__main__":

    # start_extraction()

    # conn = database.create_conn()
    # if conn is not None:
    #     conn.executemany(
    #         "INSERT INTO students VALUES(?,?)", new_students)
    #     conn.executemany(
    #         "INSERT INTO subjects VALUES(?,?)", new_courses)
    #     conn.executemany(
    #         "INSERT INTO grades VALUES(?,?,?,?,?,?)", new_grades)

    #     conn.commit()
    #     conn.close()
