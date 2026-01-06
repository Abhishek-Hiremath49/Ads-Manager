from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = [req.strip() for req in f.read().splitlines() if req.strip()]

setup(
    name="ads_manager",
    version="0.0.1",
    description="Social Media Ads Scheduler and Management",
    author="Abhishek",
    author_email="abhishekhiremath4949@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires
)