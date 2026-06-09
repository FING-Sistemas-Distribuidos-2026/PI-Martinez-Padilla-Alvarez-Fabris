# Sistemas Distribuidos

# Trabajo Práctico Integrador 

## Instalación

Clonar el repositorio junto con sus submódulos, recursivamente, usando:

```bash
git clone --recurse-submodules git@github.com:FING-Sistemas-Distribuidos-2026/PI-Martinez-Padilla-Alvarez-Fabris.git
```

Si ya se había clonado el repo anteriormente sin sus submódulos, hacer pull, y luego ejecutar:

```bash
git submodule update --init --recursive
```

### Generar secret

```bash
kubectl create secret generic raytracer-secret \
  --from-env-file=.env \
  --namespace=raytracer \
  --dry-run=client \
  -o yaml | kubectl apply -f -
```

# Hito 1: Diseño y Arquitectura

## Proyecto: Raytracer

## Grupo 1 \- Integrantes

* Lucía Alvarez  
* Adriano Fabris  
* Paula Martinez  
* Gonzalo Padilla

## Breve descripción del proyecto

El proyecto consiste de una app que permite renderizar una escena 3D a una imagen. El renderizador utiliza la técnica de raytracing, que renderiza una imagen desde la perspectiva de la cámara, simulando el comportamiento de los rayos de luz, sus reflexiones sobre superficies, las interacciones con los materiales de los objetos, etc., aproximando las leyes de la física.

El usuario puede subir a la web archivos .glb, los cuales contienen información que describe una escena 3D, incluyendo la geometría de los objetos, sus materiales, luces y cámaras. La tarea de renderizado será despachada a una cola de RabbitMQ, y eventualmente procesada por un worker que tiene embebido el renderizador escrito en C++. Una vez terminado el renderizado, la imagen resultante (en formato png) se encontrará disponible para ser descargada a través de la web.

## Diagrama de arquitectura  

![image](./images/arch.svg)

## Flujo de mensajes

![image](./images/comms.svg)

## Tecnologías elegidas: 

* Orquestador: Kubernetes  
* Broker: RabbitMQ  
* Web: Python   
* DataBase: PostgreSQL  
* Workers: Python & C++
