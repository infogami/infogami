#!/bin/sh

FAILING_FILES=(
    infogami/core/code.py
    infogami/infobase/_dbstore/indexer.py
    infogami/infobase/common.py
    infogami/infobase/tests/__init__.py
    infogami/infobase/tests/test_account.py
    infogami/infobase/tests/test_client.py
    infogami/infobase/tests/test_doctests.py
    infogami/infobase/tests/test_infobase.py
    infogami/infobase/tests/test_read.py
    infogami/infobase/tests/test_save.py
    infogami/infobase/tests/test_seq.py
    infogami/infobase/tests/test_store.py
    infogami/infobase/tests/test_writequery.py
    infogami/utils/app.py
    infogami/utils/view.py
    test/test_dbstore.py
    test/test_doctests.py
    tests/__init__.py
    tests/test_doctests.py
)

for FILEPATH in "${FAILING_FILES[@]}"; do
    echo "<<< $FILEPATH >>>"
    pytest "$FILEPATH"
    # See TODO in test/test_dbstore.py
    if [ "$FILEPATH" != "test/test_dbstore.py" ]; then
        pytest --doctest-modules "$FILEPATH";
    fi
done
