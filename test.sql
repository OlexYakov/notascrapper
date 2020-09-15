-- SQLite
SELECT
    st.name,
    max(case when sub.sname = "IIA" then gr.val end) as IIA,
    max(case when sub.sname = "COMP" then gr.val end) as "COMP",
    max(case when sub.sname = "LPA" then gr.val end) as "LPA",
    max(case when sub.sname = "SI" then gr.val end) as "SI",
    max(case when sub.sname = "CG" then gr.val end) as "CG",
    sum(
        case when sub.sname = "IIA" then gr.val else 0 end +
        case when sub.sname = "COMP" then gr.val else 0 end +
        case when sub.sname = "LPA" then gr.val else 0 end +
        case when sub.sname = "SI" then gr.val else 0 end +
        case when sub.sname = "CG" then gr.val else 0 end
    ) as media 
FROM 
    students as st 
    left join grades as gr on student_num = num
    left join subjects as sub on subject_id = id
WHERE st.name like "Oleksandr Yakovlyev" 
GROUP BY st.name