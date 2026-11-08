from backend.catalog import FOUNDATION, SNAPSHOT
from backend.schemas import ConstraintCard

DEGREE = 'https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/'
COMMON = SNAPSHOT['sources']['common_curriculum']
GE = SNAPSHOT['sources']['general_education']
NUSMODS = SNAPSHOT['sources']['nusmods']

def default_cards():
    values = [
        ('units','Complete at least 160 units','Minimum total units for the standard NUS CS degree.','hard',[{'type':'min_total_units','units':160}],[DEGREE]),
        ('core','Complete the foundation courses','CS1101S, CS1231S, CS2030S, CS2040S and the remaining prescribed foundation courses.','hard',[{'type':'require_courses','courses':FOUNDATION}],[DEGREE]),
        ('prereqs','Complete prerequisites first','Respect the prerequisite trees before taking a course.','hard',[{'type':'prerequisites'}],[NUSMODS]),
        ('coreqs','Take CS2101 and CS2103T together','Both courses must be in the same semester. CS2101 uses the matching CS2103T tutorial times (project mapping).','hard',[{'type':'corequisites'}],[DEGREE]),
        ('offering','Respect semester availability','Use actual AY2026/27 reference offerings.','hard',[{'type':'semester_availability'}],[NUSMODS]),
        ('exams','Avoid overlapping exams','Reference-year exam dates and durations must not overlap.','hard',[{'type':'exam_clashes'}],[NUSMODS]),
        ('weekly','Keep every week clash-free','Every active semester needs a complete compatible lecture, tutorial and laboratory selection.','hard',[{'type':'weekly_feasibility'}],[NUSMODS]),
        ('load','Keep a manageable workload','Planning limit: 16–24 units per active semester; at most 20 in the first. Adjust to your approved workload.','hard',[{'type':'semester_units','minimum':16,'maximum':24,'first_semester_maximum':20}],[]),
        ('focus','Complete an AI focus area','At least three AI primary courses, including one at level 4000 or above.','hard',[{'type':'focus_area','area':'Artificial Intelligence'}],[DEGREE]),
        ('gec','Complete Cultures and Connections','Choose a real approved course for the GEC pillar.','hard',[{'type':'category_units','category':'GEC','units':4}],[GE,COMMON]),
        ('gea','Complete Data Literacy','Choose GEA1000, BT1101, DSA1101 or ST1131.','hard',[{'type':'category_units','category':'GEA','units':4}],[DEGREE,GE]),
        ('gess','Complete Singapore Studies','Choose an approved GESS pillar course.','hard',[{'type':'category_units','category':'GESS','units':4}],[GE]),
        ('gen','Complete Communities and Engagement','Choose an approved GEN course. Year-long service-learning variants are browse-only until duration modelling is available.','hard',[{'type':'category_units','category':'GEN','units':4}],[COMMON,GE]),
        ('idcd','Complete interdisciplinary education','12 distinct units: at least two ID courses and no more than one CD course. Category allocations do not reuse a course.','hard',[{'type':'category_units','category':'ID_CD','units':12}],[COMMON]),
        ('duration','Prefer finishing within 8 semesters','Prefer a four-year path; the search may use the longer horizon when needed.','soft',[{'type':'finish_by','semester':8}],[]),
        ('balance','Aim for 20 units per semester','Prefer a balanced workload across active semesters.','soft',[{'type':'workload_target','units':20}],[]),
    ]
    return [ConstraintCard(id=id,title=title,description=desc,strength=strength,source='default',rules=rules,source_urls=urls)
            for id,title,desc,strength,rules,urls in values]
