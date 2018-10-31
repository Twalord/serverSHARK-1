import pygit2, os, shutil, re, datetime, gc, timeit


def map_database(db):
    keymap = dict()
    plugin_schema = db.plugin_schema
    project_db = db.project

    open_collections = []
    open_collections.append(project_db)
    visited_collections = []

    while (len(open_collections) != 0):

        current_collection = open_collections.pop()
        for doc in plugin_schema.find():
            for subdoc in doc["collections"]:
                for subsubdoc in subdoc["fields"]:
                    if "reference_to" in subsubdoc:
                        if (subsubdoc["reference_to"] == current_collection.name):
                            found_collection = db[subdoc["collection_name"]]
                            if not (found_collection in open_collections):
                                if not (found_collection in visited_collections):
                                    open_collections.append(found_collection)
                                    if current_collection.name in keymap:
                                        keymap[current_collection.name].append(found_collection.name)
                                    else:
                                        keymap[current_collection.name] = [found_collection.name]

        visited_collections.append(current_collection)

    # for some reason issue collection appears twice so I put up another filter
    final_collections = []
    for col in visited_collections:
        if col not in final_collections:
            final_collections.append(col)

    for col in final_collections:
        if col.name not in keymap:
            keymap[col.name] = []

    return keymap


def create_local_repo(vcsdoc, path):

    url = vcsdoc["url"]
    repourl = "git" + url[5:]
    if os.path.isdir(path):
        shutil.rmtree(path)

    repo = pygit2.clone_repository(repourl, path)

    return repo


def was_vcsshark_executed(vcs_col, proj_id):

    vcsshark_executed = False
    if vcs_col.find({"project_id": proj_id}).count() > 0:
        vcsshark_executed = True

    return  vcsshark_executed


def get_time():
    return timeit.default_timer()


def validate_commits(repo, vcsdoc, commit_col):

    vcsid = vcsdoc["_id"]
    db_commit_hexs = []
    for db_commit in commit_col.find({"vcs_system_id": vcsid}):
        db_commit_hexs.append(db_commit["revision_hash"])
    total_commit_hexs = db_commit_hexs.copy()

    db_commit_count = len(db_commit_hexs)
    commit_count = 0

    for commit in repo.walk(repo.head.target, pygit2.GIT_SORT_TIME):
        if not commit.hex in total_commit_hexs:
            time = datetime.datetime.utcfromtimestamp(commit.commit_time)
            if time < vcsdoc["last_updated"]:
                total_commit_hexs.append(commit.hex)
                commit_count += 1

    # inspired by vcsshark gitparser.py
    references = set(repo.listall_references())

    regex = re.compile('^refs/tags')
    tags = set(filter(lambda r: regex.match(r), repo.listall_references()))

    branches = references - tags

    for branch in branches:
        commit = repo.lookup_reference(branch).peel()
        # Walk through every child
        for child in repo.walk(commit.id,
                               pygit2.GIT_SORT_TIME | pygit2.GIT_SORT_TOPOLOGICAL):
            if not child.hex in total_commit_hexs:
                time = datetime.datetime.utcfromtimestamp(child.commit_time)
                if time < vcsdoc["last_updated"]:
                    total_commit_hexs.append(child.hex)
                    commit_count += 1

    for hex in total_commit_hexs:
        if hex in db_commit_hexs:
            db_commit_hexs.remove(hex)

    unmatched_commits = len(db_commit_hexs)
    db_commit_hexs = []

    for db_commit in commit_col.find({"vcs_system_id": vcsid}):
        db_commit_hexs.append(db_commit["revision_hash"])

    for hex in db_commit_hexs:
        if hex in total_commit_hexs:
            total_commit_hexs.remove(hex)

    missing_commits = len(total_commit_hexs)

    results = "commits in db: " + str(db_commit_count) + " unmatched commits: " + str(
        unmatched_commits) + " missing commits: " + str(missing_commits)

    return results


def validate_file_action(repo, vcsid, commit_col, file_action_col, file_col):

    counter = 0
    file_action_counter = 0
    validated_file_actions = 0

    unvalidated_file_actions = 0

    for db_commit in commit_col.find({"vcs_system_id": vcsid}).batch_size(30):

        unvalidated_file_actions_ids = []
        for db_file_action in file_action_col.find(
                {"commit_id": db_commit["_id"]}).batch_size(30):
            if not db_file_action["_id"] in unvalidated_file_actions_ids:
                unvalidated_file_actions_ids.append(db_file_action["_id"])
        file_action_counter += len(unvalidated_file_actions_ids)

        hex = db_commit["revision_hash"]

        online_commit = repo.revparse_single(hex)

        SIMILARITY_THRESHOLD = 50

        filepath = ''
        filesize = 0
        linesadded = 0
        linesremoved = 0
        fileisbinary = None
        filemode = ''

        if online_commit.parents:
            for parent in online_commit.parents:
                diff = repo.diff(parent, online_commit, context_lines=0,
                                 interhunk_lines=1)

                opts = pygit2.GIT_DIFF_FIND_RENAMES | pygit2.GIT_DIFF_FIND_COPIES
                diff.find_similar(opts, SIMILARITY_THRESHOLD,
                                  SIMILARITY_THRESHOLD)

                already_checked_file_paths = set()
                for patch in diff:

                    # Only if the filepath was not processed before, add new file
                    if patch.delta.new_file.path in already_checked_file_paths:
                        continue

                    # Check change mode
                    mode = 'X'
                    if patch.delta.status == 1:
                        mode = 'A'
                    elif patch.delta.status == 2:
                        mode = 'D'
                    elif patch.delta.status == 3:
                        mode = 'M'
                    elif patch.delta.status == 4:
                        mode = 'R'
                    elif patch.delta.status == 5:
                        mode = 'C'
                    elif patch.delta.status == 6:
                        mode = 'I'
                    elif patch.delta.status == 7:
                        mode = 'U'
                    elif patch.delta.status == 8:
                        mode = 'T'

                    filepath = patch.delta.new_file.path
                    filesize = patch.delta.new_file.size
                    linesadded = patch.line_stats[1]
                    linesremoved = patch.line_stats[2]
                    fileisbinary = patch.delta.is_binary
                    filemode = mode

                    counter += 1

                    already_checked_file_paths.add(patch.delta.new_file.path)

                    for db_file_action in file_action_col.find(
                            {"commit_id": db_commit["_id"]}).batch_size(8):

                        db_file = None

                        # for file in db.file.find({"_id": db_file_action["file_id"]},
                        #                         no_cursor_timeout=True):
                        for file in file_col.find({"_id": db_file_action["file_id"]}):
                            db_file = file

                        identical = True

                        if not filepath == db_file["path"]:
                            identical = False
                        if not filesize == db_file_action["size_at_commit"]:
                            identical = False
                        if not linesadded == db_file_action["lines_added"]:
                            identical = False
                        if not linesremoved == db_file_action["lines_deleted"]:
                            identical = False
                        if not fileisbinary == db_file_action["is_binary"]:
                            identical = False
                        if not filemode == db_file_action["mode"]:
                            identical = False

                        if identical:
                            if db_file_action["_id"] in unvalidated_file_actions_ids:
                                validated_file_actions += 1
                                unvalidated_file_actions_ids.remove(db_file_action["_id"])

        else:
            diff = online_commit.tree.diff_to_tree(context_lines=0, interhunk_lines=1)

            for patch in diff:

                filepath = patch.delta.new_file.path
                filemode = 'A'

                counter += 1

                for db_file_action in file_action_col.find(
                        {"commit_id": db_commit["_id"]}).batch_size(8):

                    db_file = None

                    for file in file_col.find({"_id": db_file_action["file_id"]}).batch_size(
                            30):
                        db_file = file

                    identical = True

                    # for initial commit filesize and linesadded never match but checking filepath should be enough
                    if not filepath == db_file["path"]:
                        identical = False
                    if not filemode == db_file_action["mode"]:
                        identical = False

                    if identical:
                        validated_file_actions += 1
                        unvalidated_file_actions_ids.remove(db_file_action["_id"])

        unvalidated_file_actions += len(unvalidated_file_actions_ids)

    results = (" file_actions found: " + str(counter) + " unmatched file_actions: " + str(
        unvalidated_file_actions) + " missing file_actions: " + str(
        file_action_counter - validated_file_actions))

    return results


def was_coastshark_executed(vcsid, code_entity_state_col, commit_col):

    coastshark_executed = False

    for db_commit in commit_col.find({"vcs_system_id": vcsid}).batch_size(30):
        if code_entity_state_col.find({"commit_id": db_commit["_id"]}).count() > 0:
            coastshark_executed = True
            break

    return coastshark_executed


def validate_code_entity_states(repo, vcsid, path, commit_col, code_entity_state_col):

    unvalidated_code_entity_states = 0
    total_code_entity_states = 0
    missing_code_entity_states = 0

    for db_commit in commit_col.find({"vcs_system_id": vcsid}).batch_size(30):

        commit = repo.get(db_commit["revision_hash"])
        commit_id = commit.hex
        ref = repo.create_reference('refs/tags/temp', commit_id)
        repo.checkout(ref)
        unvalidated_code_entity_state_longnames = []

        for db_code_entity_state in code_entity_state_col.find(
                {"commit_id": db_commit["_id"]}):
            unvalidated_code_entity_state_longnames.append(
                db_code_entity_state["long_name"])

        total_code_entity_states += len(unvalidated_code_entity_state_longnames)

        for root, dirs, files in os.walk(path):

            for file in files:

                if file.endswith('.py') or file.endswith('.java'):

                    filepath = os.path.join(root, file)
                    filepath = filepath.replace(path + "/", '')
                    if filepath in unvalidated_code_entity_state_longnames:
                        unvalidated_code_entity_state_longnames.remove(filepath)
                    else:
                        missing_code_entity_states += 1

        unvalidated_code_entity_states += len(unvalidated_code_entity_state_longnames)

        repo.reset(repo.head.target.hex, pygit2.GIT_RESET_HARD)
        ref.delete()

    results = (" code_entity_states found: " + str(
        total_code_entity_states) + " unmatched code_entity_states: " + str(
        unvalidated_code_entity_states) + " missing code_entity_states: " + str(
        missing_code_entity_states))

    return results


def delete_local_repo(path):

    if os.path.isdir(path):
        shutil.rmtree(path)
