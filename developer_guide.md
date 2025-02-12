# NZDPU - Developer Guide 📖

This is a guide for developers of the NZDPU WIS back-end, showing best-practices and guidelines.

## Contents

 - [Alembic](#alembic)
   - [Update first revision](#update-first-revision-init)
   - [Update second revision](#update-second-revision-form-specific)
     - [Target database is not up to date](#target-database-is-not-up-to-date)
     - [Update second revision - reprise](#update-second-revision---reprise)
     - [CLI commands to bring up database](#cli-commands-to-bring-up-database)
 - [Submissions](#submissions)
   - [Structure](#structure)
   - [SubmissionManager](#class-submissionmanager)
     - [create](#create)
     - [load](#load)
     - [update](#update)
   - [RevisionManager](#class-revisionmanager)
     - [update](#update-1)

## Alembic

Database schema migrations are handled by Alembic.
There is also some data migration taking place in the first migration revision.

Since the DB is relying on a JSON schema not present in the metadata, trying to generate a new migration using `alembic revision --autogenerate` will just result in a revision dropping all form tables.

For this, migrations have to be managed manually.

Let's go step by step.

### Update first revision (init)
The first migration revision, called "init", will create and populate all WIS tables. The revision does not only create the tables, but does also, for some tables, populate data accordingly to the form we want to import. The data used is stored at `migration_tools/data`, and is updated by issuing the command `python -m cli.manage_forms generate-migration <path_to_form_scema>`. Just issuing this command before upgrading to the first revision will do the trick.

### Update second revision (form-specific)

In regards to the second revision, however, things get a little trickier: as said before, trying to generate a new migration will result in alembic wanting to drop all tables which do not belong to the metadata.

So, in order to obtain the code to the last migration revision, tables need to be created "the old way" first using [CLI commands](#cli-commands-to-bring-up-database), then auto-generating a new revision will give us the needed alembic commands, in the `downgrade` function of the new revision. More on this in the following lines, but first a very important remark: almebic won't let you create a new revision if your database is not "up to date", which for alembic means that the revision you're at corresponds to the revision marked as `head`.

#### Target database is not up to date
So you should start from a clean DB to issue all the [CLI commands](#cli-commands-to-bring-up-database), but then you won't be able to make alembic generate a new revision, because your database won't be updated. But you can't bring alembic up to date and then call the CLI commands either, because that will fail.

You probably already figured at this point, that the easiest way to overcome this problem is to issue `alembic upgrade head` first, then call the [CLI commands](#cli-commands-to-bring-up-database) preceded by `python -m cli.manage_db drop-all -y`.

Another way was to just go straight with the CLI commands, and then creating the table alembic checks for keeping track of revisions, but that's probably a little but more complicated.

#### Update second revision - reprise
So once we have understood all the "target database up to date" issue, it's time to finally save this second migration.
You have brought up a new, fresh and functioning clean state of the DB, with all the tables and columns and rows you need, to make the form you loaded work. Wonderful. Now, issuing `alembic revision --autogenerate` will generate a new revision which actually DROPS almost all the tables. This is because these tables are not present in the metadata, so for alembic they don't exist. But if we look in the `downgrade` function of the revision (yes, it's the function that gets called when we go back a revision) we will find a lot of CREATE TABLE statements! Yay! And those are te ones we need to copy, and paste back into the penultimate revision's script, in the `upgrade` function (which is by logic the one which gets called when we go UP a revision). Save this revision, and delete the revision you just created (the one with all the DROP table statements in `upgrade`), and push. A new, updated revision has been created!

#### CLI commands to bring up database
```
python -m cli.manage_db create-all
python -m cli.manage_db create-user <username> <password> [--superuser]
python -m cli.manage_forms <path_to_form>
```

## Submissions

Submissions are a crucial part of the Web Information System, they can be pretty big and some functions require to iterate over them multiple time, potentially causing overhead.

For this, two helper classes have been created to handle the CRU(D) operations on submissions and revisions: `SubmissionManager` and `RevisionManager`.

### Structure

First of all, a primer on the submissions structure.

 - Each submission is defined by a row in the `wis_obj` table, though this row does not include all the information of a submission.
 - The information for a submission is spread around in multiple tables, each holding the information related to one particular form.
 - Each submission has a hierarchical structure, made of one big parent **form**, and many smaller **sub-forms**.
 - Each form has `obj_id` and `value_id` columns.
   - The `obj_id` column refers to the submission ID.
   - The `value_id` column, used only in sub-forms, refers to the value set in its parent form for the sub-form column, acting as a foreign key to associate the child form to the parent form.
 - Every column in the forms, with the exception of columns `id`, `obj_id`, `value_id`, is defined by a row in the `wis_column_def` table, holding information about the field.
 - Eventual constraints and choice sets for a particular field are defined in rows of the `wis_column_view` table.

It comes without saying that in order to gather information about a single submission, a lot of potential overhead can be created if one were to query each column every single time.

Luckily, the DB model allows us to gather all of this information in a single query, as per the following structure:

`wis_table_view` -> `wis_table_def` -> `wis_column_def` -> `wis_column_view`

Every table definition in the WIS database is linked to a table view, and all the columns of a table definition are linked to it. Column definitions and column views are linked by a one-to-many relationship as well, where the column definition act as the parent.

Having knowledge of this structure, and knowing also that rows of the `wis_obj` table possess a `table_view_id` column, it's easy to understand that only one query is needed to get all the necessary information for entering or loading a submission: it is enough to query the table view with the table view ID of the submission object, and all the data is there.

### _class_ `SubmissionManager`
```
args:
- session (sqlalchemy.ext.asyncio.AsyncSession): The DB session.
```

`SessionManager` is designed to provide all those methods needed for CRUD operations on submission (except delete). Those methods are `create()`, `load()` and `update()`.

Import:
```python
from app.routers.utils import SubmissionManager
```

#### `create()`

Creates a new submission, with values if provided (in the `SubmissionCreate` object).

_args_
 - `submission` _SubmissionCreate_: The submission data.
 - `current_uder_id` _int_: The ID of the current user.
 - `name` _str, optional_: The submission's name. Defaults to `""`.

Examples:

##### create one submission
```Python
# always need to be inside of a SQLAlchemy session
async with session() as _session:
    # init the submissions submitter
    submission_manager = SubmissionManager(_session)
    # trigger the entrypoint to load all data
    async with submission_manager:
        # give it to insert_data to perform inserts
        await submission_manager.insert_data(values_to_insert)
```

##### create multiple submissions
There isn't at the moment a best-practice on multiple submissions insert, and async for inserts is not supported (could create concerning side-effects).

The suggested way for now is just to re-initialize the `SubmissionManager` and call `create()` at each iteration for each submission to be inserted.

#### `load()`
Loads all data from a submission.

_args_
 - `submission_id` _int_: A submission identifier.


Examples:

##### load one submission
```python
# we always need to be inside a SQLAlchemy session
async with session() as _session:
    # init the submission loader
    sumission_manager = SubmissionManager(_session)
    # trigger the async entrypoint to load all data
    async with sumission_manager:
        # load the submission
        submission = await sumission_manager.load(submission_id)
```
##### load multiple submissions
```python
submissions = []
async with session() as _session:
    sumission_manager = SubmissionManager(_session)
    # trigger the entrypoint outside of loop
    async with sumission_manager:
        # now iterate to get valued submissions
        for submission_id in submission_ids:
            submission = await sumission_manager.load(submission_id)
            submissions.append(submission)
            # or
            submissions.append(await sumission_manager.load(submission_id))
```
##### load multiple submissions using async
```python
# import utility class and type from asyncio
from asyncio import Task, TaskGroup

async with session() as _session:
    sumission_manager = SubmissionManager(_session)
    # init an empty list for asyncio tasks
    tasks: list[Task] = []
    # trigger the entrypoint for TaskGroup outside of loop as well
    async with TaskGroup() as tg, sumission_manager:
        # iterate through multiple submission IDs
        for submission_id in submission_ids:
            # for each loop append a task to the tasks list
            tasks.append(tg.create_task(sumission_manager.load(submission_id)))
    # outside the async context manager,
    # call result() on all Task objects to get submissions
    submissions = [task.result() for task in tasks]
```

#### ` update()`
Updates the values of an empty submitted submission.

_args_
 - `submission_id` _int_: The submission's ID.
 - `submission` _RevisionUpdate_: The submission's values.

Examples:

##### update one (empty) submission
```Python
# always need to be inside of a SQLAlchemy session
async with session() as _session:
    # init the submissions submitter
    submission_manager = SubmissionManager(_session, submission_id)
    # trigger the entrypoint to load all data
    async with submission_manager:
        # update the submission
        await submission_manager.update(values_to_insert)
```

### _class_ `RevisionManager`
```
args:
- session (sqlalchemy.ext.asyncio.AsyncSession): The DB session.
```

Inherits from `SubmissionManager`, overriding the `update()` method.

Import:
```python
from app.routers.utils import SubmissionManager
```

#### `update()`
Different from `SubmissionManager`'s `update()` method, as its main purposes are **generation of new revisions and draft updates**.

_args_
 - `submission` _SubmissionObj_: The old submission object.
 - `new_values` _dict[str, Any]_: The new values.
 - `restatements` _dict[str, str]_: The revision's restatements.
 - `current_user_id` _int_: The ID of the user submitting the submission revision.
`create_submission` _bool, optional_: Whether to create a new submission object for the current revision, or update an existing one (draft case). Defaults to False.
 - `status` _SubmissionObjStatusEnum, optional_ = SubmissionObjStatusEnum.PUBLISHED: The submission's status. Defaults to `SubmissionObjStatusEnum.published`

Examples:

##### create a new revision
```python
async with session() as _session:
    # as usual, initialize the revision manager
    revision_manager = RevisionManager(_session)
        # trigger the entrypoint to load old data
        async with revision_manager:
            # we can use SubmissionManager's methods, here to load data
            # of an older submission
            old_submission = revision_manager.load(old_submission.id)
            # then we call update with `create_submission=True` to
            # create the new revision
            submission = await revision_manager.update(
                submission=old_submission,
                new_values=data.values,  # `data` is the request payload
                restatements=data.restatements,
                current_user_id=current_user.id,
                create_submission=True,
            )
```

##### update a draft
```python
async with session() as _session:
    revision_manager = RevisionManager(_session)
        async with revision_manager:
            old_submission = revision_manager.load(old_submission.id)
            # here we insert the logic to determinte whether a new
            # submission object should be created, directly in the
            # `create_submission` parameter
            submission = await revision_manager.update(
                submission=old_submission,
                new_values=data.values,  # `data` is the request payload
                restatements=data.restatements,
                current_user_id=current_user.id,
                # create a new submission only if the status of the submission
                # is `None` or `"published"`
                create_submission=old_submission.status
                in [None, SubmissionObjStatusEnum.PUBLISHED],
            )
```


**NOTE: ATM the method handling restatements does not accept restatements from the payload body directly, but they have to be restructured like this:**
```python
restatement_data = {}
    # expand restatement_data with restatements
    for key, value in data.restatements.items():  # `data` is the request payload
        if isinstance(value, list):
            for item in value:
                restatement_data.update(item)
        else:
            restatement_data[key] = value
```



Happy coding ✌
