from setuptools import setup, find_packages

def get_requirements(path):
    content = open(path).read()
    return [req for req in content.split("\n") if req != "" and not req.startswith("#")]

setup_args = {
    "name": "higlass_proxy",
    "version": 0.2,
    "description": "Proxy for jupyter for higlass daemons using unix sockets",
    "url": "https://github.com/hkariti/higlass_proxy",
    "author": "Hagai Kariti",
    "author_email": "hkariti@gmail.com",
    "keywords": ["higlass", "jupyter"],
    "install_requires": get_requirements("requirements.txt"),
    "packages": find_packages(),

}

setup(**setup_args)
