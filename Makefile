PYFILES = *.py post-install/osg-post-install ./make-client-tarball

_default:
	@echo "Nothing to make. Try make check"

check:
	pylint -E $(PYFILES)

lint:
	-pylint --rcfile=pylintrc $(PYFILES) --reports=n --disable=R0801 --persistent=y | grep -E -v '^[CR][[:digit:]]+'

fulllint:
	-pylint --rcfile=pylintrc $(PYFILES)
# ignore return code in above


.PHONY: _default check lint fulllint

