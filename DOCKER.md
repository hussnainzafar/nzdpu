# Docker in NZDPU-wis
There are two docker files.

* Dockerfile
  * For developers to use
  * Builds the package itself in a builder container 
* Dockerfile.cicd
  * For CICD to use
  * Expects the package to be already created and in the `./dist` directory

## Dockerfile
### Requirements
None

### Build Steps
```shell
docker build .
```

## Dockerfile.cicd
### Requirements
built wheel in ./dist
### Build Steps
```shell
# Clean old cache
rm -rf dist
# Install python builder
python3 -m pip install build
python3 -m build
docker build . -f Dockerfile.cicd
```