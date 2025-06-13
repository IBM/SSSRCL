# SSSRCL
IBM Spectrum Scale System Remote Code Load Management Script

Remote code load for ESS needs a service container running and SSS API
Server hosted on IBM Utility host. To setup service container and SSS
API server at utility node required below steps should be followed.
There are some pre-requisites required to run Service container and

SSS API server at IBM Utility node.
Pre-requisite:
    a) IBM Utility node should have access to public network using “campus”
    network interface. Here is an example of the “campus” network which
    connect Utility host to Internet to make a SSH tunnel to service
    container. This must have pre-requite for Remote Code Loader feature.

    [rcladmin@utility1 ~]$ ifconfig campus
        campus: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 9.114.12.77  netmask 255.255.252.0  broadcast 9.114.15.255
        inet6 fe80::f0b:b511:be70:ef20  prefixlen 64  scopeid 0x20<link>
        ether a0:42:3f:4d:ca:b8  txqueuelen 1000  (Ethernet)
        RX packets 96789  bytes 7836564 (7.4 MiB)
        RX errors 0  dropped 1066  overruns 0  frame 0
        TX packets 8219  bytes 1769097 (1.6 MiB)
        TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0

    “campus” interface which has a public IP assigned with proper Gateway
    and DNS name resolution configured. Without public network user can opt
    for Proxy server accessed to connect IBM Utility node to internet.

    b)	A system admin must have access to “root” user to create two users.
        I.	rcladmin – RCL Admin user is required to host Remote Code Load Service Container.
        II.	apiadmin- API Admin user is required to host SSS API Server Container.

    c)	For hosting SSS API Server container required a prior experience
    in SS MoS (gpfs.scaleapi) Design and it’s principle. This SSS API Server
    is based on SS MoS server, in other words this SSS API Server is a cut
    down version of the SS MoS API Server without scale functionality.

    d) Another important design change with this SSS API Server is, it is only
    designed to run on single host environment. This means this API Server
    cannot communicate with other SSS API Server and exchange state and data.

    e) User must also know how to replace the SSL certificate of the API Server.
    As of now when SSS API Server will start it will create a new self-signed
    certificate and placed on /home/apiadmin/keys folder.

    f) By default, this self-signed certificate will be imported to SSS API Server
    to start server.

    g) This certificate MUST be replaced with customer owned CA signed or customer
    should generate a new self-signed organization certificate and import it.

    h) By default, SSS API server container preconfigured with two users name “apiadmin” and “apiuser”.
        I.	“apiadmin” is a superuser can be able to change any Authorization.
            If any new user wants to get added to this SSS API Server container then it needs expertise of SS API Server framework and use.
        II.	“apiuser” is a non-privileged user.

    i) Hosts file consideration on IBM Utility host is very important
    for RCL Service Container and SSS API Server to get worked. See utilityBareMetal_hosts
    file in repo and it should be replaced in the /etc/hosts file, should be present
    on IBM Utility host before starting any of the containers.

    j) Customer should have correct entitlemnt to pull the Remote Code Load Container image from IBM Container Repository.

        $ podman login cp.icr.io --username cp --password <API_Key>


# Setting up Remote Code Load Service Container
a)	Make sure rcladmin user and rcladmin group has been already created on utility host. If user is not present, please add user using below command. Login to IBM Utility node using root user and add below user.

    $ useradd rcladmin
    $ passwd rcladmin

Set required password for this user.

b)	Now user has been added so now we need to add above user in sudoers.d folder. Create a file under /etc/sudoers.d/ folder named rcladmin_sudoers and copy and paste below content to rcladmin_sudoers file.

    rcladmin     ALL=(ALL)       NOPASSWD: /usr/sbin/dmidecode, /bin/cat, /sys/devices/virtual/dmi/id/product_serial

c)	Now logged out with root user and login with rcladmin user. Make sure user should be able to login with rcladmin user. This rcladmin user is a non-privileged user and will be used to host Remote Code Load service container.

d)	To host service container, we need a utility program named “rclmgr” and a configuration file named “rclmgr.yml”. This file can be obtained from github.ibm,com (https://github.ibm.com/IBMSpectrumScale/SSSRCL/) . “rclmgr” file will be used to host and start service container. This utility will read “rclmgr.yml” file and start container. User can check out the above-mentioned repository at IBM Utility host under “rcladmin” user to use “rclmgr” utility. Here is the help text of “rclmgr” utility.

    [rcladmin@utility1 ~]$ ./rclmgr -h
    usage: rclmgr [-h] [-c CONFIG_FILE] [-x] [-i] [-f IMAGE_FILE_NAME] [-n] [-net NETWORK_NAME] [-r]

    optional arguments:
    -h, --help            show this help message and exit
    -c CONFIG_FILE, --config CONFIG_FILE
                            Specify custom Config file name. Default: rclmgr.yml
    -x, --force           Container operation with force.
    -i, --install         Install container image.
    -f IMAGE_FILE_NAME, --file IMAGE_FILE_NAME
                            Specify the Image file name in tarball format.
    -n, --create-network  Creates podman CNI network other than default podman CNI network
    -net NETWORK_NAME, --network-name NETWORK_NAME
                            Creates podman CNI network with default name rcl_network.
    -r, --run             Runs Remote Code Load Service Container.

    This script run Remote Code Load Service Container image for EMS node.

e)	Running service container require “./rclmgr -r” command to get invoked from the folder where this utility program has been placed. In this case “rclmgr” utility is placed in /home/rcladmin/ folder. As of now we need to “export ALLOW_RCLMGR=1” to use this utility.

    [rcladmin@utility1 ~]$ export ALLOW_RCLMGR=1
    [rcladmin@utility1 ~]$ ./rclmgr -r

    Now we can see service container has been hosted at utility host but not yet started. To start service container, we need to systemd service of this container.

    [rcladmin@utility1 ~]$ systemctl --user start container-utilityBareMetal-rcl-official.service

    This will start service container servie and we can see our container is in running status using below command.

    [rcladmin@utility1 ~]$ systemctl --user status container-utilityBareMetal-rcl-official.service

    After starting the service IBM Utility host should be visible inside IBM Service Portal. Let’s login and see the node is visible or not.

f)	Now let’s looks closely at how this rclmgr utility pulled the container image and start the container. We have a configuration file name rclmgr.yml in same directory which contain vital information to pull the container image and start the container. Here is the sample content of the rclmgr.yml file.

%YAML 1.1
---

CONTAINER:
    # Hostname and nick name of the container
    CONTAINER_HOSTNAME: utilityBareMetal-rcl-official
    CONTAINER_DOMAIN_NAME: gpfs.local

    # ------------------------------------------------------
    # Optional container network.
    # Make sure the network has been create prior using rclmgr command.
    # By default podman default CNI network will be used
    # ------------------------------------------------------
    # CONTAINER_NETWORK_NAME: ess_network
    # ------------------------------------------------------

    # Installer node hostname and the
    # IP address of Mgmt and the FSP/BMC interface
    UTILITY_HOSTNAME: utilityBareMetal

    CAMPUS_INTERFACE: campus
    CAMPUS_INTERFACE_IP: 9.114.12.77

    RAS_INTERFACE: virbr1
    RAS_INTERFACE_IP: 10.23.16.1

    # ------------------------------------------------------
    # SSH Port, Default 10022
    # ------------------------------------------------------
    SSH_PORT: 10022

    # ------------------------------------------------------
    # Container image version detail
    # ------------------------------------------------------
    # Image Name
    IMAGE_NAME: quay.io/sumitkuo_ibm/sss_rcl

    # Image Version
    IMAGE_VERSION: 6.2.3.0

    # ----------------------------------
    # log and backup location. These are the location on the container hosting node.
    # ----------------------------------
    LOG: /home/rcladmin/log
    BKUP: /home/rcladmin/backup

    If we can closely see the content of this file, we are pulling the container image from a container repository named quay.io and the image version is 0212-05. We will move this to IBM valid repository before GA.

    CAMPUS_INTERFACE_IP must be replaced with correct “campus”interface IP as of now. Domain name used here is “gpfs.local”.

    Rest of the information in this YAML file should not be touched.

g)	Here is the IBM Service Portal URL should be used to login and see the IBM Utility host eligible for service.
    a.	Production:
        i.	https://rsc1.tms.stglabs.ibm.com/
        ii.	https://rsc2.tms.stglabs.ibm.com/
        iii.	https://rsc3.tms.stglabs.ibm.com/

    As of now all service containers will be registered at rsc1.tms.stglabs.ibm.com. Let’s login and see. User should have proper access to login to IBM Service Portal. Please consult IBM Service Portal admin to get the user created. IBM Intranet ID should be used to login to IBM Service Portal.

    Now click on “View all connected ESS systems” and it will take use to a page where he can see registered IBM Utility node.

    In case IBM utility node is not listed then please restart service container service again using systemctl command as shown below:

    [rcladmin@utility1 ~]$ systemctl --user stop container-utilityBareMetal-rcl-official.service
    [rcladmin@utility1 ~]$ systemctl --user start container-utilityBareMetal-rcl-official.service

    This is known issue will fix soon. Once system started listing click on “Start Terminal” to start the SSH tunnel session and login to service container for further servicing on IBM Sepcturm Scale System nodes.

    Now click on “Service access” and provide “Authentication Id” as “rcladmin” or “rcluser” depending on the user access privileged. By default, the password for “rcladmin” and “rcluser” is “cluster”.

    “Root access” is NOT allowed to IBM Service Container to consider the privacy and security of the customer environment.

    Give some correct reason to connect to this node. This is required for auditing purpose. Once all input provided click on “Connect” to login to service container.

    Type password of the user selected for login to service portal and get into SSH prompt.

    Now we have logged in and ready to service SSS nodes using “essctl” command.

h)	To service SSS nodes we need to use a command named “essctl”. This is a command line utility will work with SSS API Server hosted on IBM Utility host to invoke the SSS deployment artifacts. For “essctl” command to work we must have SSS API Service up and running on IBM Utility host. See SSS API Server Installation and Configuration for more info. Here is a help of “essctl” command for a reference.

    [rcladmin@utilityBareMetal-rcl-official ~]$ /usr/lpp/mmfs/bin/essctl
    IBM Storage Scale System Deployment Administration CLI interface

    Usage:
    essctl [flags]
    essctl [command]

    Available Commands:
    authorization authorization commands
    essmgmt       ESS Management commands
    essrun        Essrun commands
    node          node commands
    operation     operation commands

    Flags:
        --bearer                     if true, OIDC_TOKEN will be read from the env and be sent as the Authorization Bearer header for the request. Must be used with --url
        --cert string                path to the client certificate file used for authentication
        --debug string[="stderr"]    enable debug logging for the current request. Accepts an absolute file path to store the logs in the form of --debug=<file>. If no file path is provided, stderr will be used
        --domain string              Sets the domain for the request (default "DeploymentDomain")
    -h, --help                       help for essctl
        --insecure-skip-tls-verify   if true, the server's certificate will not be checked for validity. This will make your HTTPS connections insecure
        --json                       display output in json format
        --key string                 path to the client certificate private key file used for authentication
        --url string                 send the request over https to the specified endpoint <FQDN/IP>:<port>. An IPv6 address must be wrapped in square brackets such as [IPv6]:<port>. If a port is not specified, 46443 will be used
        --version                    essctl build information

    Use "essctl [command] --help" for more information about a command.

    Once service of SSS nodes has been performed user should logout and close the service portal window to prevent unauthorised access of the service controller.

    Now close the Browser window.

i)	As we have mentioned above service container can be access via two different user “rcladmin” or “rcluser”.
    a.	“rcladmin” user is a power user who can perform update or deploy SSS nodes.
    b.	“rcluser” is a normal read only user who can login to service container and see the health of the SSS nodes. This user is not allowed to perform “Update” or “Deploy” of the SSS nodes.
