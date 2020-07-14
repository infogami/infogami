#!/bin/bash

# Run from the infogami root dir
cd ..
OL_DIR=openlibrary-$RANDOM
git clone https://github.com/internetarchive/openlibrary $OL_DIR
rm -rf $OL_DIR/vendor/infogami
ln -sf $(pwd)/infogami $OL_DIR/vendor/infogami

cd $OL_DIR
pip install -r requirements_test.txt
pytest openlibrary/tests openlibrary/mocks openlibrary/olbase openlibrary/plugins openlibrary/utils openlibrary/catalog openlibrary/coverstore scripts/tests
