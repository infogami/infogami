#!/bin/bash

# Clone latest openlibrary adjacent to where infogami is
cd ..
# Add a random number to the end here, so that it can run ~in parallel (?)
OL_DIR=openlibrary-$RANDOM
git clone https://github.com/internetarchive/openlibrary $OL_DIR

# Make it use the current infogami
pushd $OL_DIR && make git && popd;
rm -rf $OL_DIR/vendor/infogami
ln -sf $(pwd)/infogami $OL_DIR/vendor/infogami

# Install requirements / run pytests
cd $OL_DIR
pip install -r requirements_test.txt
# TODO: Use make test-py once https://github.com/internetarchive/openlibrary/pull/3582 merged
pytest openlibrary/tests openlibrary/mocks openlibrary/olbase openlibrary/plugins openlibrary/utils openlibrary/catalog openlibrary/coverstore scripts/tests
