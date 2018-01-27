.PHONY: publish

publish:
	python setup.py sdist bdist_wheel
	twine upload dist/*
	rm -fr build dist .egg bloop.egg-info
