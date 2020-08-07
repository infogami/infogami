#!/bin/sh

FAILING_FILES=(
    infogami/core/dbupgrade.py
    infogami/infobase/_json.py
    infogami/infobase/bulkupload.py
    infogami/plugins/i18n/code.py
    infogami/plugins/links/db.py
    infogami/plugins/pages/code.py
    infogami/plugins/review/code.py
    infogami/plugins/review/db.py
    infogami/plugins/wikitemplates/code.py
    migration/migrate-0.4-0.5.py
    test/bug_239238.py
)

for FILEPATH in "${FAILING_FILES[@]}"; do
    echo "<<< $FILEPATH >>>"
    pytest "$FILEPATH"
    pytest --doctest-modules "$FILEPATH"
done
