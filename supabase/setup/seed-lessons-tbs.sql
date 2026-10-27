-- Seeds the Academy ELO tab with TBS classes and their Enabling Learning
-- Objectives into the platoon workspace ("The Basic School").
-- Requires alter-lessons.sql (or a fresh 02-schema.sql). Safe to re-run:
-- classes that already exist are skipped, and ELOs are only inserted for a
-- class that has none yet. After seeding, press Re-index all on Foundry ELO
-- so Discussions can search the ELOs.

with platoon as (
  select id
  from public.workspaces
  where lower(trim(name)) = lower('The Basic School')
  limit 1
),
classes (sort_order, title) as (
  values
    (1, 'Tactical Combat Casualty Care'),
    (2, 'Decision Making'),
    (3, 'Standards of Conduct'),
    (4, 'Responsibilities of the Interior Guard'),
    (5, 'Role of the Chaplain'),
    (6, 'Operational Terms and Graphics'),
    (7, 'Cardinal Virtues'),
    (8, 'Marine Corps Uniforms and Customs and Courtesies'),
    (9, 'Human Performance Methodologies'),
    (10, 'Intro to Tactical Breathing, Mindset, and Mindfulness')
)
insert into public.lessons (workspace_id, title, sort_order)
select platoon.id, classes.title, classes.sort_order
from classes
cross join platoon
where not exists (
  select 1
  from public.lessons existing
  where existing.workspace_id = platoon.id
    and existing.title = classes.title
);

with platoon as (
  select id
  from public.workspaces
  where lower(trim(name)) = lower('The Basic School')
  limit 1
),
seed (lesson_title, position, text, code, is_async) as (
  values
    -- Tactical Combat Casualty Care
    ('Tactical Combat Casualty Care', 1, 'Without the aid of references, identify components of the IFAK used to control bleeding without error.', 'MCS-MED-1001a', false),
    ('Tactical Combat Casualty Care', 2, 'Given a scenario and a simulated casualty, utilize components of the IFAK used to treat airway obstruction to stabilize life-threatening injury.', 'MCS-MED-1001b', false),
    ('Tactical Combat Casualty Care', 3, 'Given a scenario and a simulated casualty, utilize pressure dressing components to stabilize life-threatening injury.', 'MCS-MED-1001c', false),
    ('Tactical Combat Casualty Care', 4, 'Given casualties with various types of injuries and a secure position out of effective enemy fire, prioritize casualties for CASEVAC to prevent further injury or death.', 'MCS-MED-1501a', false),
    ('Tactical Combat Casualty Care', 5, 'Given casualties with various types of injuries and a secure position out of effective enemy fire, determine requirements for the evacuation platform in order to prepare the pick-up site.', 'MCS-MED-1501b', false),
    ('Tactical Combat Casualty Care', 6, 'Given a simulated combatant scenario and a casualty while still under active enemy fire or threat, return fire and take cover to prevent harm or additional casualties while prioritizing the suppression of enemy fire and fire superiority.', 'MCS-TCCC-1006a', false),
    ('Tactical Combat Casualty Care', 7, 'Given a simulated combatant scenario and a casualty while still under active enemy fire or threat, direct casualty to remain engaged to prevent harm, or additional casualties while prioritizing the suppression of enemy fire and fire superiority.', 'MCS-TCCC-1006b', false),
    ('Tactical Combat Casualty Care', 8, 'Given a simulated combatant scenario and a casualty while still under active enemy fire or threat, direct casualty to perform self-aid to prevent harm, or additional casualties while prioritizing the suppression of enemy fire and fire superiority.', 'MCS-TCCC-1006c', false),
    ('Tactical Combat Casualty Care', 9, 'Given a simulated combatant scenario and a casualty while still under active enemy fire or threat, move casualty behind cover to prevent harm, or additional casualties while prioritizing the suppression of enemy fire and fire superiority.', 'MCS-TCCC-1006d', false),
    ('Tactical Combat Casualty Care', 10, 'Given a simulated combatant scenario and a casualty while still under active enemy fire or threat, control life-threatening bleeding to prevent harm, or additional casualties while prioritizing the suppression of enemy fire and fire superiority.', 'MCS-TCCC-1006e', false),
    ('Tactical Combat Casualty Care', 11, 'Given Marines, a casualty or casualties, communications equipment. Direct the evacuation of casualties To evacuate casualties in a timely manner with minimal interruption to the mission, while maintaining accountability.', 'MCS-MED-1501', false),
    ('Tactical Combat Casualty Care', 12, 'Given an Individual First Aid Kit (IFAK) and references. Inventory an Individual First Aid Kit (IFAK) To ensure it is complete and serviceable, per the references.', 'MCS-MED-1001', false),
    ('Tactical Combat Casualty Care', 13, 'Given a combatant scenario and a casualty while still under active enemy fire or threat. Perform Care Under Fire To prevent harm or additional casualties while prioritizing the suppression of enemy fire and fire superiority.', 'MCS-TCCC-1006', false),

    -- Decision Making
    ('Decision Making', 1, 'Without the aid of references, identify the steps of the OODA Cycle without omission.', 'MCS-CMBH-1002a', true),
    ('Decision Making', 2, 'Without the aid of references, identify decision-making variables without omission.', 'MCS-CMBH-1002b', true),
    ('Decision Making', 3, 'Without the aid of references, define analytical decision-making without omission.', 'MCS-CMBH-1002c', true),
    ('Decision Making', 4, 'Without the aid of references, define recognition-primed decision-making without omission.', 'MCS-CMBH-1002d', true),
    ('Decision Making', 5, 'Without the aid of references, identify the role of the main effort in accomplishing the commander’s intent in accordance with MCDP 1 Warfighting.', 'MCS-LDR-1009n', false),
    ('Decision Making', 6, 'Given a mission and with the aid of references, utilize operation terms and graphics to communicate decisions with clarity.', 'MCS-LDR-1503a', false),

    -- Standards of Conduct
    ('Standards of Conduct', 1, 'Without the aid of references, identify a potential course of action a commander may take in response to a Marine testing positive for an illegal substance in accordance with MCO 5300.17.', 'MCS-VALU-1002a', true),
    ('Standards of Conduct', 2, 'Without the aid of references, identify the tenets of the alcohol abuse prevention program in accordance with MCO 5300.17.', 'MCS-VALU-1002b', true),
    ('Standards of Conduct', 3, 'Without the aid of references, define equal opportunity in accordance with MCO P5354.1 w/Ch 1.', 'MCS-VALU-1002c', true),
    ('Standards of Conduct', 4, 'Without the aid of references, identify the purpose of the Marine Corps Equal Opportunity policy without omission.', 'MCS-VALU-1002d', true),
    ('Standards of Conduct', 5, 'Without the aid of references, define hazing without omission.', 'MCS-VALU-1002e', true),
    ('Standards of Conduct', 6, 'Without the aid of references, identify the purpose of the Marine Corps Hazing policy without omission.', 'MCS-VALU-1002f', true),
    ('Standards of Conduct', 7, 'Without the aid of references, define fraternization without omission.', 'MCS-VALU-1002g', true),
    ('Standards of Conduct', 8, 'Without the aid of references, identify the purpose of the Marine Corps Fraternization policy without omission.', 'MCS-VALU-1002h', true),
    ('Standards of Conduct', 9, 'Given a scenario and references, determine if fraternization has occurred to uphold good order and discipline.', 'MCS-VALU-1002i', true),
    ('Standards of Conduct', 10, 'Without the aid of references, define sexual harassment without omission.', 'MCS-VALU-2002a', false),
    ('Standards of Conduct', 11, 'Without the aid of references, define sexual assault without omission.', 'MCS-VALU-2002b', false),

    -- Responsibilities of the Interior Guard
    ('Responsibilities of the Interior Guard', 1, 'Without the aid of references, identify types of guard forces without error.', 'MCS-ATFP-1501a', true),
    ('Responsibilities of the Interior Guard', 2, 'Without the aid of references, identify the purpose of the interior guard without omission.', 'MCS-ATFP-1501b', true),
    ('Responsibilities of the Interior Guard', 3, 'Without the aid of references, identify the composition of the interior guard without omission.', 'MCS-ATFP-1501c', true),
    ('Responsibilities of the Interior Guard', 4, 'Without the aid of references, identify the levels of the force continuum in sequence, without omission.', 'MCS-ATFP-1501d', true),
    ('Responsibilities of the Interior Guard', 5, 'Without the aid of references, define deadly force without omission.', 'MCS-ATFP-1501e', true),
    ('Responsibilities of the Interior Guard', 6, 'Without the aid of references, identify circumstances when deadly force is authorized without error.', 'MCS-ATFP-1501f', true),
    ('Responsibilities of the Interior Guard', 7, 'Without the aid of references, identify justifications for the use of deadly force without omission.', 'MCS-ATFP-1501g', true),
    ('Responsibilities of the Interior Guard', 8, 'Given assigned duty, orders and directives, perform the duties of The Basic School Junior Officer of the Day (JOOD) of the interior guard to ensure good order and discipline and ensure compliance with orders and directives.', 'MCS-ATFP-1501h', true),
    ('Responsibilities of the Interior Guard', 9, 'Given assigned duty, orders and directives, perform the duties of the company duty officer within the interior guard to maintain good order and discipline and ensure compliance with orders and directives.', 'MCS-ATFP-1501i', true),

    -- Role of the Chaplain
    ('Role of the Chaplain', 1, 'Without the aid of reference, identify suicide warning signs to determine if someone is suicidal.', 'MCS-VALU-1010b', false),
    ('Role of the Chaplain', 2, 'Without the aid of reference, identify suicide prevention resources without omission.', 'MCS-VALU-1010c', false),

    -- Operational Terms and Graphics
    ('Operational Terms and Graphics', 1, 'Given a mission and with the aid of references, utilize operation terms and graphics to communicate decisions with clarity.', 'MCS-LDR-1503a', false),

    -- Cardinal Virtues
    ('Cardinal Virtues', 1, 'Without the aid of references, describe the concept “moral injury” without omission.', 'MCS-LDR-2005b', true),
    ('Cardinal Virtues', 2, 'Without the aid of references, define the four cardinal virtues (Fortitude, Temperance, Prudence, Justice) without omission.', 'MCS-VALU-1002m', false),
    ('Cardinal Virtues', 3, 'While part of a Marine Corps unit and without the aid of references, make ethical decisions in the absence of guidance in accordance with The Basic School’s Five Horizontal Themes.', 'MCS-VALU-1002l', false),

    -- Marine Corps Uniforms and Customs and Courtesies
    ('Marine Corps Uniforms and Customs and Courtesies', 1, 'Without the aid of references, explain the significance of the Marine Corps emblem without omission.', 'MCS-HIST-1003a', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 2, 'Without the aid of references, explain the significance of the scarlet trouser stripe without omission.', 'MCS-HIST-1003b', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 3, 'Without the aid of references, explain the significance of the dress and service uniform buttons without omission.', 'MCS-HIST-1003c', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 4, 'Without the aid of references, explain the significance of the French fourragere without omission.', 'MCS-HIST-1003d', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 5, 'Given individual field equipment and cleaning supplies, clean equipment to ensure equipment is clean and serviceable.', 'MCS-UNIF-1001a', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 6, 'Given individual field equipment and a storage space, store equipment to ensure it remains serviceable.', 'MCS-UNIF-1001b', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 7, 'Given a scenario, identify the appropriate reference(s) to ensure clothing is clean, serviceable, marked, and fits according to the uniform regulations.', 'MCS-UNIF-1002a', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 8, 'Given individual clothing, a ruler, a marking kit, sewing kit, cleaning material and references, mark individual clothing to ensure clothing is clean, serviceable, marked, and fits according to the uniform regulations.', 'MCS-UNIF-1002b', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 9, 'With the aid of references, identify grooming standards in accordance with MCO P1020.34 Marine Corps Uniform Regulations without error.', 'MCS-UNIF-1003a', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 10, 'With the aid of references, identify weight and body fat standards in accordance with MCO P1020.34 Marine Corps Uniform Regulations without error.', 'MCS-UNIF-1003b', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 11, 'With the aid of references, identify inappropriate civilian attire as described by MCO P1020.34 Marine Corps Uniform Regulations.', 'MCS-UNIF-1003c', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 12, 'With the aid of references, match civilian attire with corresponding military uniform in accordance with MCO P1020.34.', 'MCS-UNIF-1003d', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 13, 'Without the aid of references, identify physical training uniforms in accordance with MCO P1020.34.', 'MCS-UNIF-1004a', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 14, 'Without the aid of references, identify all service uniforms in accordance with MCO P1020.34.', 'MCS-UNIF-1004b', false),
    ('Marine Corps Uniforms and Customs and Courtesies', 15, 'Given the requirement, stand a uniform inspection in accordance with MCO P1020.34.', 'MCS-UNIF-1004c', false),

    -- Human Performance Methodologies
    ('Human Performance Methodologies', 1, 'Without the aid of references, identify the four domains of Marine Fitness without omission.', 'MCS-COND-2001g', false),

    -- Intro to Tactical Breathing, Mindset, and Mindfulness
    ('Intro to Tactical Breathing, Mindset, and Mindfulness', 1, 'Without the aid of references, identify the four domains of Marine Fitness without omission.', 'MCS-COND-2001g', false),
    ('Intro to Tactical Breathing, Mindset, and Mindfulness', 2, 'Without the aid of references, understand the principles and requirements of operating effectively in harsh environmental conditions.', 'MCS-LDR-1006c', false)
)
insert into public.lesson_objectives (lesson_id, workspace_id, position, text, code, is_async)
select lesson.id, platoon.id, seed.position, seed.text, seed.code, seed.is_async
from seed
cross join platoon
join public.lessons lesson
  on lesson.workspace_id = platoon.id
  and lesson.title = seed.lesson_title
where not exists (
  select 1
  from public.lesson_objectives existing
  where existing.lesson_id = lesson.id
);
