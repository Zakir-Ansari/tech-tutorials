# CI CD with GitHub Actions

Table of content
1. Manual Deployment to EC2 on AWS
2. GitHub Actions
3. Automation for spring boot projects
4. Hands On


## Manual Deployment to EC2 on AWS
For this tutorial, we are going to use a simple Spring Boot rest application
with a simple controller. We will perform manual steps of building and deploying
the app to EC2 instance on AWS.



manual workflow diagram: Code >> Image >> Docker Container >> Endpoint
<img src="./../resources/github-actions-ci-cd/CI-CD-Local.png">
1. First, we will create a jar file of our spring boot application using maven command `mvn clean install`
2. We will then create an image of our application using docker and push it to docker hub.
3. We will then pull the image from docker hub to our EC2 instance and run the container.
4. We will then access our application using the public IP of our EC2 instance.



Command to build the package:
`./mvnw clean package -DskipTests`

After this, you will see a jar file in the target folder.
Now, we will create a docker image of our application and push it to docker hub.


Now let's create a docker file in the root directory of our project with the following content:

```dockerfile
FROM eclipse-temurin:25
WORKDIR /app
# Copy the built JAR file into the container
COPY target/*.jar app.jar
# Expose the application port (if needed)
EXPOSE 8080
# Run the application
ENTRYPOINT ["java", "-jar", "app.jar"]
```

Now, run the following command to build the docker image:
`docker build -t <build-package-name>:latest`

Then to run the container locally, use the following command:
`docker run -d -p 8080:8080 <build-package-name>:latest`

as an output, you will see a hash value which is the container id. You can also check the container status in docker dashboard.

You will now be able to access your application at `http://localhost:8080/` (assuming your controller is mapped to /).

What we have done so far is we have containerized our application, and we have an image now.
Next, we will push this image to docker hub so that we can pull it from our EC2 instance.

First you need to create an account on docker hub.
Then you will have to push the image to a registry which can be anything, and in our case it is docker hub.

From that registry we will pull the image to our EC2 instance and run the container there.

Flow diagram with github actions
<img src="">

But for now, we will do it manually.
1. First, we will login to our docker hub account using the following command:
`docker login`
2. Then we will tag our image with the following command:
`docker tag <build-package-name>:latest <docker-hub-username>/<repository-name>:latest`
3. Finally, we will push the image to docker hub using the following command:
`docker push <docker-hub-username>/<repository-name>:latest`
Expected output:
```bash
$ docker push zakir01/spring-boot-ci-demo:latest
The push refers to repository [docker.io/zakir01/spring-boot-ci-demo]
456eee9f1cc2: Pushed 
c1631b0cc5ba: Pushed 
69b037921f81: Pushed 
4b9f8c886789: Pushed 
64671de9b827: Pushed 
b40150c1c271: Pushed 
5f6278b6d85f: Pushed 
latest: digest: sha256:335df406579860d8be83cfa5f85eadd63e0466ad0f2f74992da0f5a1d2f753be size: 856
```


Now, login to your AWS account and create an EC2 instance. If you don't have an account, follow the registration process and create a free tier account.
<image for Ec2 resource dashboard>

Click on Launch Instance and follow the steps to create an instance. 
fill a Name and select AMI (preferably Amazon Linux 2) and select an instance type (t2.micro is free tier eligible). 
Now, is the time you have to use or create a key pair to access your instance.
Now, why do we need a key pair?
You can use a key pair to securely connect to your instance. This will help us to login via terminal and run commands on our instance.

Click on create a new key pair (if you don't have one) and give it a name (for this demo, let's take it as demo-keypair).
Then click on download key pair and save the file in a secure location. This file will have a .pem extension, and you will need it to connect to your instance.
When prompted, store the private key in a secure and accessible location on your computer. You will need it later to connect to your instance.

Then in Network settings, put Firewall(security groups) as Create security group and allow SSH, HTTP and HTTPS traffic to be connected from anywhere (for this sake of this tutorial). 
Finally, click on Launch instance and wait for the instance to be created.

< Image of EC2 Network Settings>
Rest all we can keep as default for this tutorial. You can explore more options and settings while creating an instance.
Now you can launch the instance and wait for it to be in running state. 

Once it is running, you can connect to it using the key pair you created.
To connect to your instance, you can use the following command in your terminal:
`ssh -i /path/to/your/demo-keypair.pem ec2-user@<public-ip-address>`
Make sure to replace the path with the actual path where you saved your key pair and the public IP address with the actual public IP address of your instance.

Expected Output:
```bash
$ ssh -i demo-keypair.pem ec2-user@13.49.67.207
   ,     #_
   ~\_  ####_        Amazon Linux 2023
  ~~  \_#####\
  ~~     \###|
  ~~       \#/ ___   https://aws.amazon.com/linux/amazon-linux-2023
   ~~       V~' '->
    ~~~         /
      ~~._.   _/
         _/ _/
       _/m/'
[ec2-user@ip-172-31-33-64 ~]$ 
```

Now, we are connected to our EC2 instance. Update the instance with `sudo yum update -y`
Now, we will install docker on our instance using the following command:
```bash
$ sudo yum install docker -y
```

Once docker is installed, check the docker version using the following command:
```bash
$ docker --version
Docker version 25.0.14, build 0bab007
```

Now, we will start the docker service using the following command:
```bash
$ sudo systemctl start docker
```

Now, we will enable docker to start on boot using the following command:
```bash
$ sudo systemctl enable docker
```

In order to give the current user i.e. ec2-user permission to run docker commands without sudo, we will add the user to the docker group using the following command:
```bash
$ sudo usermod -aG docker $USER
```

Note: You won't be able to see the docker processes (command: `docker ps`)until you log out and log back in. So, log out of your instance and log back in using the same ssh command as before.

Its time to pull the docker image from docker hub to our EC2 instance using the following command:
```bash
$ docker pull <docker-hub-username>/<repository-name>:latest
```
Expected output:
```bash
$ docker pull zakir01/spring-boot-ci-demo
Using default tag: latest
latest: Pulling from zakir01/spring-boot-ci-demo
b40150c1c271: Pull complete 
5f6278b6d85f: Pull complete 
69b037921f81: Pull complete 
4f4fb700ef54: Pull complete 
456eee9f1cc2: Pull complete 
c1631b0cc5ba: Pull complete 
64671de9b827: Pull complete 
Digest: sha256:335df406579860d8be83cfa5f85eadd63e0466ad0f2f74992da0f5a1d2f753be
Status: Downloaded newer image for zakir01/spring-boot-ci-demo:latest
docker.io/zakir01/spring-boot-ci-demo:latest
```

Run below command to check if the image is pulled successfully:
```bash
$ docker images
REPOSITORY                    TAG       IMAGE ID       CREATED       SIZE
zakir01/spring-boot-ci-demo   latest    e060086a33ee   2 hours ago   412MB
```

Great! Now we have the image on our EC2 instance. Next, we will run the container using the following command:
```bash
$ docker run -d -p 8080:8080 <docker-hub-username>/<repository-name>:latest
```
Expected output:
```bash
$ docker run -d -p 8080:8080 zakir01/spring-boot-ci-demo:latest
c732490bc3da28d44e0b19cc39fbfea82a98be138a6dffecf32c1dcc03a449f2


$ docker ps
CONTAINER ID   IMAGE                         COMMAND               CREATED          STATUS          PORTS                                       NAMES
c732490bc3da   zakir01/spring-boot-ci-demo   "java -jar app.jar"   42 seconds ago   Up 40 seconds   0.0.0.0:8080->8080/tcp, :::8080->8080/tcp   quizzical_austin
```

Now, how do we access?
To access your application, you can use the public IP address of your EC2 instance followed by the port number. In our case, it will be `http://<public-ip-address>:8080/`.

But you might get into a problem where you won't be able to access your application. This is because of the security group settings of your EC2 instance.
And the reason is, in the security group settings, we have allowed traffic on port 8080 only from the same security group. So, we need to change it to allow traffic from anywhere.
We will add a new inbound rule to allow traffic on port 8080 from anywhere. To do this, go to the EC2 dashboard, click on Security Groups, select the security group associated with your instance, and click on Inbound rules. Then click on Edit inbound rules and add a new rule with the following settings:
- Type: Custom TCP
- Protocol: TCP
- Port range: 8080
- Source: Anywhere (0.0.0.0/0)
- Description: Allow traffic on port 8080 from anywhere
- Finally, click on Save rules.

Now, you should be able to access your application at `http://<public-ip-address>:8080/`.

In next section we will go to Next level and automate this whole process using GitHub Actions. We will create a workflow that will build our application, create a docker image, push it to docker hub, and then deploy it to our EC2 instance automatically whenever we push changes to our repository.