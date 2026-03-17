# Artifact Evaluation: SSA without Dominance for Higher-Order Programs

## First Look

```sh
docker run -it mimir
```

## Persistent Storage

In order to conveniently work with the docker image, you have to create a storage on the host side that you can later on inspect on your host machine without entering the docker image.
1. Create the host storage (do this only once):
   ```sh
   mkdir -p ${PWD}/pldi

   # Extract original home directory
   docker create --name temp mimir
   docker cp temp:/home/pldi/. ${PWD}/pldi/
   docker rm temp
   ```
2. Now enter the image with proper permissions:
   ```sh
   docker run -it --rm -v ${PWD}/pldi:/home/pldi --user $(id -u):$(id -g) mimir
   ```
   Anything you do will appear in `${PWD}/pldi` on your host machine.

##
