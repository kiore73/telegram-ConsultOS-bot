async def seed_questionnaire(session):
    """Populates the database with the new, structured questionnaire."""
    logging.info("Seeding new questionnaire data...")
    main_questionnaire = Questionnaire(title="Основной опросник")
    session.add(main_questionnaire)
    await session.flush()

    question_definitions = [
        # ... (all question definitions from the user's file) ...
    ]

    question_map = {}
    for q_def in question_definitions:
        q = Question(questionnaire_id=main_questionnaire.id, text=q_def['text'], type=q_def['type'])
        session.add(q)
        question_map[q_def['str_id']] = q
    
    await session.flush()

    logic_definitions = [
        # ... (all logic definitions from the user's file) ...
    ]

    for logic_def in logic_definitions:
        # ... (logic to add QuestionLogic entries) ...
        pass

    await session.commit()
    logging.info("Questionnaire data seeded successfully.")