from typing import Dict, List, Tuple
from tinydb import TinyDB, Query, where

db = TinyDB("db.json")
students_db = db.table("students")
courses_db = db.table("courses")
grades_db = db.table("grades")


def best_score(scores: Dict) -> str:
    best = 0
    for scores in scores.values():
        for value in scores.values():
            if value.isnumeric() and eval(value) > best:
                best = eval(value)
    return best if best >= 10 else 0


def get_student_grades(num=None, **kwargs):
    name = None
    if num is None:
        if "num" in kwargs.keys():
            num = kwargs["num"]
        elif "name" in kwargs.keys():
            name = kwargs["name"]
        else:
            raise Exception("Invalid call, use named args 'num' or 'name'")

    if name is not None:
        raise NotImplementedError

    else:
        grades = grades_db.search(where("num") == num)
        for grade in grades:
            course_name = courses_db.get(
                where("id") == grade["course_id"])["name"]
            print(f"{course_name} - {best_score(grade['scores'])}")


whilelist = ["01000213", "01000287", "01000265", "01000224", "01000230",
             "01000276", "01000301", "01000259", "01000241", "01000298"]

whilelist2 = ["01000287", "01000265",
              "01000276", "01000301", "01000241"]


def student_average(grades: List[Dict]) -> Tuple[int, float]:
    n_courses = 0
    grade_sum = 0
    for course in grades:
        if course["course_id"] not in whilelist2:
            continue
        grade = best_score(course["scores"])
        grade_sum += grade
        if grade >= 10:
            n_courses += 1

    avg = grade_sum/n_courses if n_courses != 0 else 0

    return (n_courses, avg)


def get_top_students(n=20):
    top_list = []
    for student in students_db:
        scores = grades_db.search(where("num") == student["num"])
        (n_courses, avg) = student_average(scores)
        if n_courses == len(whilelist2):
            top_list.append((student["name"], (n_courses, avg)))

    top_list.sort(key=lambda e: e[1][1], reverse=True)

    for (name, (n, avg)) in top_list[:n]:
        print(f"{name} - {avg:.2f} {n}")

# get_student_grades("2015231448")


get_top_students()
