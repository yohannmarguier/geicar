from setuptools import find_packages, setup


package_name = "so_arm101"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="EcoCar team",
    maintainer_email="ecocar@example.com",
    description="Bounded, opt-in dance demo for a powered SO-101 follower arm.",
    license="GPL-2.0-only",
    entry_points={
        "console_scripts": [
            "dance_node = so_arm101.dance_node:main",
            "diagnose = so_arm101.diagnose:main",
        ]
    },
)
