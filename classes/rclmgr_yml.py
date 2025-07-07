#!/usr/bin/python3
# -----------------------------------------------------------------------------
# Licensed Materials - Property of IBM
#
# (C) Copyright IBM Corp.  2020  All Rights Reserved
#
# US Government Users Restricted Rights - Use, duplication or disclosure
# restricted by GSA ADP Schedule Contract with IBM Corp.
#
# -----------------------------------------------------------------------------
#
# File name: rclmgr_yml.py
# Description: Class to check and create rclmgr YML file
# -----------------------------------------------------------------------------
#
# Changelog:
# YYYY/MM/DD
# 2024/04/03 Initial WIP
#
# -----------------------------------------------------------------------------

import yaml
import os
import ipaddress
import re
import logging
import datetime
import sys
from netifaces import AF_INET, AF_INET6, AF_LINK, AF_PACKET, AF_BRIDGE
import netifaces
import ipaddress
import socket
import shutil
import argparse
import sqlite3
import subprocess
import json


# SSR netblock
SSR_NETBLOCK = "10.111.222.100/30"

#CNI netblock
CNI_NETBLOCK = "10.88.0.0/16"

# RAS netblock
RAS_NETBLOCK = "10.23.16.0/29"

# RAS bridge IP
RAS_IP = "10.23.16.1"

# RCL ENDPOINTS
RCL_ENDPOINTS = [
                "xrsc-front-srv-1.southdata.ibm.com",
                "xrsc-front-srv-2.southdata.ibm.com",
                "xrsc-front-srv-3.eastdata.ibm.com",
                "xrsc-front-srv-4.eastdata.ibm.com"
                ]


STATIC_rclmgr_YML = {
    'CONTAINER_HOSTNAME': 'utilityBareMetal-rcl-official',
    'CAMPUS_INTERFACE': 'campus',
    'RAS_INTERFACE': 'virbr1',
    'RAS_INTERFACE_IP': '10.23.16.1',
    'IMAGE_NAME': 'cp.icr.io/cp/scalesystem/sss_rcl',
    'SSH_PORT': '10022',
    'LOG': '/home/rcladmin/log',
    'BKUP': '/home/rcladmin/backup'
}

CONFIG_rclmgr_YML = {
    'CONTAINER_DOMAIN_NAME': 'gpfs.local',
    'UTILITY_HOSTNAME': 'utilityBareMetal',
    'CAMPUS_INTERFACE_IP': '192.168.100.10',
    'IMAGE_VERSION': '6.2.3.0'
}


class rclmgr_yml(object):
    """
        Class to manage rclmgr YML file creation, checks and start the container

        RC 0  = Success
        RC 1  = Generic error
        RC 2  = Cannot create output dir
        RC 3  = Cannot resolve all endpoints
        RC 4  = No IPv4 address or netmask configured on interface[s] nor bridge[s]
        RC 5  = Interface does not exist
        RC 6  = Cannot reach all endpoints
        RC 7  = RAS IP is not th expected one
        RC 8  = Domain not configured in OS
        RC 9  = Container is already UP
        RC 10 = Could not delete image
        RC 11 = FREE
        RC 12 = Failure writing YML file
        RC 13 = Initial file does not have required fields or has wrong values for them
        RC 14 = FREE
        RC 15 = Tool is not run as rcladmin user
        RC 16 = FREE
        RC 17 = FREE
        RC 18 = FREE
        RC 19 = FREE
        RC 20 = FREE
        RC 21 = Cannot copy rclmgr into classes directory
        RC 22 = Cannot import rclmgr
        RC 23 = Cannot run rclmgr readconf
        RC 24 = Start container returned an error
        RC 25 = FREE
        RC 26 = podman binary does not exist
        RC 27 = FREE
        RC 28 = nmcli binary does not exist
        RC 29 = FREE
        RC 30 = FREE
        RC 31 = SSR SQL DB file does not exists
        RC 32 = FREE
        RC 33 = FREE
        RC 34 = FREE
        RC 35 = FREE
        RC 36 = FREE
        RC 37 = FREE
        RC 38 = FREE
        RC 39 = FREE
        RC 40 = FREE
        RC 41 = FREE
        RC 42 = FREE
        RC 43 = FREE
        RC 44 = FREE
        RC 45 = FREE
        RC 46 = FREE
        RC 47 = FREE
        RC 48 = FREE
        RC 49 = FREE
        RC 50 = log and/or backup are not a directory
        RC 51 = Container is resolvable for automatic bridge setup
    """

    def __init__(
            self,
            verbose,
            filename
            ):
        self.filename = "rclmgr.yml"
        self.verbose = verbose
        self.output_dir = "./logs"
        self.total_errors = 0
        self.merged_cfg = {}
        self.st_time = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.log_file = self.output_dir + 'RCL_' + self.st_time + ".log"
        self.run_log = self.__start_logger()
        self.static_rclmgr_yml = STATIC_rclmgr_YML
        self.config_rclmgr_yml = CONFIG_rclmgr_YML
        currentDirectory = os.getcwd()
        self.IMAGE_TARBALL = filename

        self.cfg_loaded, self.cfg = self.__load_yml_file()
        if self.cfg_loaded:
            self.run_log.debug(
                "The YML file was loaded"
            )
        else:
            self.run_log.error(
                "There was an issue loading the rclmgr.yml file"
            )
            self.run_log.debug(
                "Going to terminate with RC 1"
            )
            sys.exit(1)
        self.container = self.cfg['CONTAINER']
        self.static_NOK = self.__check_static_vars()
        self.config_OK = self.__check_config_keys()
        if self.static_NOK or not(self.config_OK):
            self.run_log.error(
                "The file " +
                self.filename +
                " does not have all the required entries or do not " +
                "match valid values. Please do not modify the file manually."
            )
            self.run_log.debug(
                "Going to terminate with RC 13"
            )
            sys.exit(13)
        else:
            self.run_log.debug(
                "The file " +
                self.filename +
                " does have all the required entries."
            )

        # Lets deal with CAMPUS if applicable
        if "CAMPUS_INTERFACE" in self.container:
            self.CAMPUS_IPv4 = self.__get_IP_address(
                self.container['CAMPUS_INTERFACE'],
                "CAMPUS"
            )
        else:
            self.CAMPUS_IPv4 = self.container['CAMPUS_INTERFACE_IP']

        if self.CAMPUS_IPv4 is None:
            campus_interface_exist = self.__check_interface_exists("campus")

            if campus_interface_exist:
                self.run_log.debug("Campus interface exists.")
            else:
                self.run_log.error("Campus interface does not exist in this system")
            sys.exit(4)

        # Lets deal with RAS if applicable
        if "RAS_INTERFACE" in self.container:
            self.RAS_IPv4 = self.__get_IP_address(
                self.container['RAS_INTERFACE'],
                "RAS"
            )
        else:
            self.RAS_IPv4 = self.container['RAS_INTERFACE_IP']

        if self.RAS_IPv4 is None:
            ras_interface_exist = self.__check_interface_exists("virbr1")
            if ras_interface_exist:
                self.run_log.debug("RAS interface exists.")
            else:
                self.run_log.error("virbr1 / RAS interface does not exist in this system")
            sys.exit(4)

        # Lets deal with IMAGE_NAME if applicable
        self.IMAGE_NAME = self.container['IMAGE_NAME']
        self.IMAGE_VERSION = self.__ask_IMAGE_VERSION()

        self.run_log.debug(
            "We use UTILITY hostname to derivate names for Management. Safe option."
        )
        self.UTILITY_HOSTNAME = self.__get_UTILITY_HOSTNAME()
        self.DNS_domain = self.__get_sys_domain()

        # Lets copy rclmgr into classes dir
        self.__copy_rclmgr_into_classes()
        self.__podman_bin_exists()
        self.__nmcli_bin_exists()

        # self.__SSR_SQL_check()


    def startRCLContainer(self):
        # Print logs message
        print(
            "\nDetailed logs are located on " +
            self.output_dir +
            " directory\n"
        )
        # First we check we are root or root alike
        self.__check_rcladmin_user()

        # Hardcoded hostname name
        cont_hostname = self.static_rclmgr_yml['CONTAINER_HOSTNAME']

        container_hostname = {"CONTAINER_HOSTNAME": cont_hostname}
        contResolvable = self.__checkContNotResolvable(cont_hostname)
        if contResolvable:
            self.run_log.error(
                "Container name can be resolved. This is not supported. " +
                "Do not add the RCL container to /etc/hosts nor DNS, and try again."
            )
            self.run_log.debug(
                "Going to exit with RC=51"
            )
            sys.exit(51)
        else:
            self.run_log.debug(
                "Container name cannot be resolved in this autobridge setup"
            )

        # Lets check RAS IP is the expected one
        self.__check_RAS_IP()

        # Lets check we can resolve the endpoints
        self.__resolve_endpoints()

        # Lets check we can reach the endpoints
        self.__reach_endpoints()

        # Lets merge the container information
        self.run_log.debug(
            "Going to merge configurable parameters to be written"
        )
        self.merged_cfg.update(container_hostname)
        # We need to merge the other config parameters that are not asked
        self.merged_cfg.update({'CONTAINER_DOMAIN_NAME': self.DNS_domain})
        self.merged_cfg.update({'UTILITY_HOSTNAME': self.UTILITY_HOSTNAME})
        self.merged_cfg.update({'CAMPUS_INTERFACE_IP': self.CAMPUS_IPv4})
        self.merged_cfg.update({'IMAGE_VERSION': self.IMAGE_VERSION})
        #self.merged_cfg.update({'RAS_INTERFACE_IP': self.RAS_IPv4})

        # the static entries. We should readapt the function that does this
        self.merged_cfg.update(self.static_rclmgr_yml)
        self.run_log.debug(
            "Merge configurable parameters to be written"
        )
        # We can now write the file, update variable with data to be
        # Lets update container with the gathered values
        self.container = self.merged_cfg.copy()
        self.run_log.debug(
            "Ready to write data into YML file"
        )
        file_written = self.__write_YML_file()
        if file_written:
            self.run_log.debug(
                "YML file " +
                self.filename +
                " has succesfully been written"
            )
        else:
            self.run_log.error(
                "YML file " +
                self.filename +
                " has failed to be written"
            )
            self.run_log.debug(
                "Going to terminate with RC 12"
            )
            sys.exit(12)
        # We can now check the file
        # Reload
        self.run_log.debug(
            "Going to reload with freshly created file"
        )
        self.cfg_loaded, self.cfg = self.__load_yml_file()
        if self.cfg_loaded:
            self.run_log.debug(
                "The YML file was reloaded"
            )
        else:
            self.run_log.error(
                "There was an issue loading the rclmgr.yml file"
            )
            self.run_log.debug(
                "Going to terminate with RC 1"
            )
            sys.exit(1)
        self.run_log.debug(
            "Going to check reloaded file"
        )
        entries_NOK = self.__check_YML_entries()
        if entries_NOK:
            self.run_log.error(
                "This just created YML file CANNOT be used"
            )
        else:
            self.run_log.debug(
                "This just created YML file can be used"
            )
        # Few things can be tweaked about reloads and static
        # Not a big deal yet as check is fast
        return entries_NOK

    def __ask_IMAGE_VERSION(self):
        # User wants to change hostname we change or exit if cancel
        try:
            while True:
                self.run_log.debug(
                    "Going to ask the user for a Image Version"
                )
                IMAGE_VERSION_user = input(
                    "Please type a Image Version : "
                )
                if IMAGE_VERSION_user == "6.2.3.0":
                    break
                else:
                    print("\nImage name should be 6.2.3.0")
            return IMAGE_VERSION_user
        except KeyboardInterrupt:
            print("")
            self.run_log.error(
                "User cancelled EMS hostname input\n"
            )
            self.run_log.debug(
                "Going to terminate with RC 6"
            )
            sys.exit(6)

    def __write_YML_file(self):
        # We save original file as .bak and create new with gathered data
        to_be_file = self.output_dir + self.filename + "_" + self.st_time
        self.run_log.debug(
            "Going to move " +
            self.filename +
            " as " +
            to_be_file
        )
        os.rename(self.filename, to_be_file)
        self.run_log.debug(
            "Moved " +
            self.filename +
            " as " +
            to_be_file
        )
        container_dict = {'CONTAINER': self.merged_cfg}
        self.run_log.debug(
            "Going to write information into YML file " +
            self.filename
        )
        try:
            with open(self.filename, "w") as outfile:
                yaml.dump(container_dict, outfile, default_flow_style=False)
            self.run_log.debug(
                "Writen information into YML file " +
                self.filename
            )
            return True
        except BaseException:
            self.run_log.error(
                "Cannot write information into YML file " +
                self.filename
            )
            self.run_log.debug(
                "Going to terminate with RC 12"
            )
            sys.exit(12)


    def __checkContNotResolvable(self, containerShort):
        containerLong = containerShort + "." + self.DNS_domain

        self.run_log.debug(
            "Container short " +
            containerShort +
            " converted to FQDN " +
            containerLong
        )
        self.run_log.debug(
            "Need to check that nor short container name " +
            containerShort +
            " or long " +
            containerLong +
            " can be resolved on this auto bridge setup"
        )
        canResolve = False
        try:
            resolved_ip = socket.gethostbyname(containerShort)
            self.run_log.debug(
                "The container short name " +
                containerShort +
                " resolves to IP address " +
                resolved_ip
            )
            is_CNI_block = self.__check_IP_in_netblock(resolved_ip, CNI_NETBLOCK)
            if is_CNI_block:
                self.run_log.debug(
                    "Although it resolves this is the CNI netblock " +
                    str(CNI_NETBLOCK) +
                    " and we allow to resolve to that network"
                )
            else:
                self.run_log.debug(
                    "The resolved IP does not belong to CNI netblock " +
                    str(CNI_NETBLOCK) +
                    ". We raise an error."
                )
                self.run_log.error(
                "The container short name " +
                containerShort +
                " resolves to IP address " +
                resolved_ip
                )
                canResolve = True
        except socket.gaierror:
            self.run_log.debug(
                "The container short name " +
                containerShort +
                " does not resolve any IP address"
            )
        # Now long name
        try:
            resolved_ip = socket.gethostbyname(containerLong)
            self.run_log.debug(
                "The container long name " +
                containerLong +
                " resolves to IP address " +
                resolved_ip
            )
            is_CNI_block = self.__check_IP_in_netblock(resolved_ip, CNI_NETBLOCK)
            if is_CNI_block:
                self.run_log.debug(
                    "Although it resolves this is the CNI netblock " +
                    str(CNI_NETBLOCK) +
                    " and we allow to resolve to that network"
                )
            else:
                self.run_log.debug(
                    "The resolved IP does not belong to CNI netblock " +
                    str(CNI_NETBLOCK) +
                    ". We raise an error."
                )
                canResolve = True
        except socket.gaierror:
            self.run_log.debug(
                "The container long name " +
                containerLong +
                " does not resolve any IP address"
            )
        return canResolve


    def __get_UTILITY_HOSTNAME(self):
        self.run_log.debug(
            "Going to query UTILITY hostname"
        )
        UTILITY_HOSTNAME = "utilityBareMetal"
        self.run_log.debug(
            "The UTILITY hostname is " +
            UTILITY_HOSTNAME
        )
        return UTILITY_HOSTNAME


    def __get_sys_domain(self):
        # Lets get the domain or fail RC 8 if none
        self.run_log.debug(
            "Going to check for domain name in the system"
        )
        # Issues on changes with platform, we move to socket
        try:
            DNS_domain = socket.gethostname().split('.', 1)[1]
            self.run_log.debug(
                "Domain name in the system is " +
                DNS_domain
            )
        except IndexError:
            self.run_log.error(
                "There is no domain name configured in the system"
            )
            self.run_log.debug(
                "Going to terminate with RC 8"
            )
            sys.exit(8)
        return str(DNS_domain)


    def __create_output_dir(self):
        # Lets create the output dir
        if os.path.isdir(self.output_dir) == False:
            try:
                os.makedirs(self.output_dir)
            except BaseException:
                print(
                    self.st_time +
                    "\t FATAL ERROR: Cannot create output dir " +
                    self.output_dir
                )
                self.run_log.debug(
                    "Going to terminate with RC 2"
                )
                sys.exit(2)

    def __copy_rclmgr_into_classes(self):
        if os.path.isfile("classes/rclmgr.py") == False:
            self.run_log.debug(
                "rclmgr.py does not exist inside classes directory"
            )
            self.run_log.debug(
                "Going to copy rclmgr inside classes directory as rclmgr.py"
            )
            try:
                shutil.copyfile("rclmgr", "classes/rclmgr.py")
                self.run_log.debug(
                    "rclmgr is copied inside classes directory as rclmgr.py"
                )
            except BaseException:
                self.run_log.error(
                    "Cannot copy rclmgr into classes directory"
                )
                self.run_log.debug(
                    "Going to terminate with RC 21"
                )
                sys.exit(21)
        else:
            self.run_log.debug(
                "rclmgr.py does already exist inside classes directory"
            )

    def __start_logger(self):
        self.__create_output_dir()
        sv_log_format = '%(asctime)s %(levelname)-4s:\t %(message)s'
        logging.basicConfig(level=logging.DEBUG,
                            format=sv_log_format,
                            filename=self.log_file,
                            filemode='w')

        console = logging.StreamHandler()
        if self.verbose:
            console.setLevel(logging.DEBUG)
        else:
            console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(sv_log_format))
        logging.getLogger('').addHandler(console)
        rclmgr_yml_log = logging.getLogger(self.filename)
        return rclmgr_yml_log

    def __load_yml_file(self):
        cfg_loaded = False
        self.run_log.debug(
            "Going to check if YML file " +
            self.filename +
            " exists"
        )
        file_exists = os.path.isfile(self.filename)
        if file_exists:
            self.run_log.debug(
                "Completed check for " +
                self.filename +
                " and exists"
            )
        else:
            self.run_log.error(
                "Completed check for " +
                self.filename +
                " and does not exist"
            )
            self.run_log.debug(
                "Going to terminate with RC 1"
            )
            sys.exit(1)

        self.run_log.debug("Starting YML load of " + self.filename)
        try:
            with open(self.filename, 'r') as ymlfile:
                cfg = yaml.safe_load(ymlfile)
                self.run_log.debug(
                    "Successful load as YML from " +
                    self.filename
                )
                cfg_loaded = True
        except BaseException:
            cfg = None
            self.run_log.warning(
                "Failed to load as YML from " +
                self.filename
            )
            cfg_loaded = False
        return (cfg_loaded, cfg)

    def __is_valid_FQDN(self, hostname, domain):
        # We check is RFC1035 + RFC3696 prefered options
        self.run_log.debug(
            "Going to merge hostname " +
            hostname +
            " and domain " +
            domain
        )
        long_hostname = hostname + "." + domain
        self.run_log.debug(
            "hostname and domain merged as " +
            long_hostname
        )
        RFC3696_pref = re.compile(
            r'^(([a-zA-Z]{1})|([a-zA-Z]{1}[a-zA-Z]{1})|'
            r'([a-zA-Z]{1}[0-9]{1})|([0-9]{1}[a-zA-Z]{1})|'
            r'([a-zA-Z0-9][-.a-zA-Z0-9]{0,61}[a-zA-Z0-9]))\.'
            r'([a-zA-Z]{2,13}|[a-zA-Z0-9-]{2,30}.[a-zA-Z]{2,3})$'
        )
        self.run_log.debug("Starting FQDN check for " + long_hostname)
        good_FQDN = RFC3696_pref.match(long_hostname)
        if good_FQDN:
            self.run_log.debug(
                "Completed FQDN check for " +
                long_hostname +
                " and it aligns with RFC1035 and RFC3696 prefered format"
            )
        else:
            self.run_log.error(
                "Completed FQDN check for " +
                long_hostname +
                " and it does not align with RFC1035 and " +
                "RFC3696 prefered format"
            )
        return(good_FQDN)

    def __get_IP_address(self, interface, essnet):
        # First lets check is a good interface
        interface_exists = self.__check_interface_exists(interface)
        if interface_exists:
            self.run_log.debug(
                "The interface " +
                interface +
                " on network " +
                essnet +
                " exists"
            )
        else:
            self.run_log.error(
                "The interface " +
                interface +
                " on network " +
                essnet +
                " does not exist"
            )
            self.run_log.debug(
                "Going to terminate with RC 5"
            )
            sys.exit(5)
        # If we survive previous check lets move on
        self.run_log.debug(
            "Going to query for IP address of " +
            interface
        )
        try:
            ip_address = netifaces.ifaddresses(interface)[2][0]['addr']
        except BaseException:
            # This is either a really bad issue or that bridges are
            # already created due previous run or second container

            self.run_log.debug(
                interface +
                " does not have any IPv4 address configured. "
            )
            return None
        self.run_log.debug(
            "Main IP address of " +
            interface +
            " is " +
            ip_address
        )
        return str(ip_address)

    def __check_interface_exists(self, interface):
        # Simple check to see we have the interface is the system
        self.run_log.debug(
            "Going to check if " +
            interface +
            " exists in this system"
        )
        system_interfaces = netifaces.interfaces()
        if interface in system_interfaces:
            interface_exists = True
            self.run_log.debug(
                interface +
                " exists in this system"
            )
        else:
            interface_exists = False
            self.run_log.debug(
                interface +
                " does not exist in this system"
            )
            # We terminate here
        return interface_exists

    def __check_config_keys(self):
        self.run_log.debug(
            "Going to check if configurable keys exist on " +
            self.filename
        )
        # We do not care about values just that all keys are there
        for key in self.config_rclmgr_yml.keys():
            try:  # In case key is missing in file
                if self.container[key] == self.config_rclmgr_yml[key]:
                    # We have the key, irrelevant value
                    config_keys_OK = True
                    self.run_log.debug(
                        "Key " +
                        key +
                        " exists on " +
                        self.filename +
                        " and matches the file"
                    )
                else:
                    config_keys_OK = True
                    self.run_log.debug(
                        "Key " +
                        key +
                        " exists on " +
                        self.filename +
                        " and does not match the file"
                    )
            except KeyError:
                # we are missing some static key
                config_keys_OK = False
                self.run_log.error(
                    "Key " +
                    key +
                    " does not exist on " +
                    self.filename +
                    ". We stop the checks for more keys here"
                )
            except BaseException:
                # some other exception
                self.run_log.error(
                    "Some undetermined error when checking current YML " +
                    "file happened. If available please try to use a " +
                    "previous version of rclmgr.yml file from ./logs/. " +
                    "If that is not an option use the manufacturing base " +
                    "file. And if that is neither fixing this, please " +
                    "contact IBM support and attach all the contents of " +
                    "./logs directory into the case"
                )
                self.run_log.debug(
                    "Going to terminate with RC 1"
                )
                sys.exit(1)
        self.run_log.debug(
            "Ending check if configurable keys exist on " +
            self.filename
        )
        return config_keys_OK

    def __merge_static_cfg(self):
        if self.static_NOK:
            self.run_log.error(
                "Static entroes did not pass the test. " +
                "Cannot merge them into the config to write"
            )
        else:
            self.run_log.debug(
                "Static entries passed the test. " +
                "Merging them into the config to write"
            )
            self.merged_cfg.update(self.static_rclmgr_yml)
            self.run_log.debug("Static entries merged into config to write")

    def __check_static_vars(self):
        self.run_log.debug(
            "Going to check if static keys exist on " +
            self.filename +
            " and values are the expected ones"
        )
        # We do a check for the non configurable parameters
        static_entries_error = False
        for key in self.static_rclmgr_yml.keys():
            try:  # In case key is missing in file
                if str(self.container[key]) != str(self.static_rclmgr_yml[key]):
                    # We have the key but is not the same
                    static_entries_error = True
                    self.total_errors += 1
                    self.run_log.error(
                        "Key " +
                        key +
                        " exists on " +
                        self.filename +
                        " but value " +
                        str(self.container[key]) +
                        " is not the expected one of " +
                        self.static_rclmgr_yml[key]
                    )
                else:
                    self.run_log.debug(
                        "Key " +
                        key +
                        " exists on " +
                        self.filename +
                        " and value " +
                        str(self.container[key]) +
                        " is the expected one"
                    )
            except KeyError:
                # we are missing some static key
                static_entries_error = True
                self.total_errors += 1
                self.run_log.error(
                    "Key " +
                    key +
                    " does not exist on " +
                    self.filename +
                    ". We stop the checks here"
                )
                break
        if static_entries_error:
            self.run_log.error(
                "Ending check static keys exist on " +
                self.filename +
                " and values are not the expected ones"
            )
        else:
            self.run_log.debug(
                "Ending check static keys exist on " +
                self.filename +
                " and values are the expected ones"
            )
        return static_entries_error

    def __check_IP_in_netblock(self, IP, net_block):
        self.run_log.debug(
            "Going to check if IP " +
            str(IP) +
            " belongs to netblock " +
            str(net_block)
        )
        try:
            is_in = ipaddress.ip_address(IP) in ipaddress.ip_network(net_block)
        except ValueError:
            self.run_log.warning(
                "IP " +
                str(IP) +
                " does not seems to have a correct IPv4 format"
            )
            return False  # Is not in
        if is_in:
            self.run_log.debug(
                "IP " +
                str(IP) +
                " belongs to netblock " +
                str(net_block)
            )
        else:
            self.run_log.debug(
                "IP " +
                str(IP) +
                " does not belong to netblock " +
                str(net_block)
            )
        return is_in

    def __check_IP(self, IP_to_check):
        self.run_log.debug(
            "Going to check IP " +
            IP_to_check
        )
        try:
            IP_OK = True
            ipadd = ipaddress.ip_address(IP_to_check)
            self.run_log.debug(
                "IP has valid format"
            )
            if ipadd.version == 4:
                self.run_log.debug("IP has IPv4 format")
            else:
                IP_OK = False
                self.run_log.debug("IP does not have IPv4 format")
        except ValueError:
            IP_OK = False
            self.run_log.debug("IP does not have a valid format")
        self.run_log.debug(
            "Ending check IP " +
            IP_to_check +
            " and we return IP_OK=" +
            str(IP_OK))
        return IP_OK

    def __check_FQDN(self, hostname, domain):
        FQDN_to_check = hostname + "." + domain
        self.run_log.debug(
            "Going to check FQDN for " + FQDN_to_check)
        FQDN_is_OK = self.__is_valid_FQDN(hostname, domain)
        if FQDN_is_OK:
            self.run_log.debug(
                "Completed FQDN check for " +
                FQDN_to_check +
                " and we accept it"
            )
        else:
            self.run_log.error(
                "Completed FQDN check for " +
                FQDN_to_check +
                " and we do not accept it"
            )
        return FQDN_is_OK

    def __check_name_IP(self, hostname, ip_address):
        all_OK = True
        # Lets check here that IP and name mutually resolve each other
        self.run_log.debug(
            "Going to check if DNS name " +
            hostname +
            " and IP address " +
            ip_address +
            " mutually resolve to each other"
        )
        try:
            resolved_ip = socket.gethostbyname(hostname)
            self.run_log.debug(
                "DNS name " +
                hostname +
                " resolves to IP address " +
                resolved_ip
            )
        except socket.gaierror:
            self.run_log.error(
                "The DNS name " +
                hostname +
                " does not resolve any IP address"
            )
            all_OK = False
            return all_OK
        self.run_log.debug(
            "Going to check if resolved IP " +
            resolved_ip +
            " is the same as " +
            ip_address
        )
        if resolved_ip == ip_address:
            self.run_log.debug(
                "Resolved IP " +
                resolved_ip +
                " for DNS name " +
                hostname +
                " is the same as " +
                ip_address
            )
        else:
            self.run_log.error(
                "Resolved IP " +
                resolved_ip +
                " for DNS name " +
                hostname +
                " is not the same as " +
                ip_address
            )
            all_OK = False
            return all_OK
        self.run_log.debug(
            "Going to check if IP address " +
            ip_address +
            " resolves to " +
            hostname
        )
        try:
            resolved_names = socket.gethostbyaddr(ip_address)
            self.run_log.debug(
                "The IP address resolves to " +
                resolved_names[0] +
                " as main DNS name"
            )
        except socket.herror:
            self.run_log.error(
                "The IP address " +
                ip_address +
                " does not resolve any DNS name"
            )
            all_OK = False
            return all_OK
        # Lets first look if we have the name as main resolved name
        # If not lets then see if there is any alias and check those
        if hostname == resolved_names[0]:
            self.run_log.debug(
                "The main DNS name of IP address " +
                ip_address +
                " matches the hostname " +
                hostname
            )
        else:
            self.run_log.debug(
                "The main DNS name of IP address " +
                ip_address +
                " does not match the hostname " +
                hostname
            )
            if len(resolved_names[1]) > 0:
                # We have alias lets not fail yet
                self.run_log.debug(
                    "The main DNS name of IP address " +
                    ip_address +
                    " does not match the hostname " +
                    hostname +
                    " but there are " +
                    str(len(resolved_names[1])) +
                    " alias to check"
                )
                alias_matches = False
                for alias in resolved_names[1]:
                    self.run_log.debug(
                        "Going to check if alias " +
                        str(alias) +
                        " matches hostname " +
                        str(hostname)
                    )
                    if alias == hostname:
                        alias_matches = True
                        self.run_log.debug(
                            "An alias DNS name of IP address " +
                            ip_address +
                            " matches the hostname " +
                            hostname
                        )
                        all_OK = True
                        break
                    if not alias_matches:
                        self.run_log.debug(
                            "Alias DNS name of IP address " +
                            ip_address +
                            " does not match the hostname " +
                            hostname
                        )
                        all_OK = False
                if all_OK:
                    self.run_log.debug(
                        "There is one alias match, we move on"
                    )
                else:
                    self.run_log.error(
                        "No alias DNS name of IP address " +
                        ip_address +
                        " does match the hostname " +
                        hostname
                    )
            else:
                # No main hit and no alias exists
                self.run_log.error(
                    "The main DNS name of IP address " +
                    ip_address +
                    " does not match the hostname " +
                    hostname +
                    " and there are no alias to check"
                )
                all_OK = False
        return all_OK

    def __check_YML_entries(self):
        if self.static_NOK:
            self.run_log.error(
                "Static keys did not pass the test. " +
                "Did you manually edit the file?"
            )
            # We fail here, no further checks
            config_entries_NOK = True
            return config_entries_NOK
        else:
            self.__merge_static_cfg()
            self.run_log.debug(
                "Static config passed the tests and been merged to be written"
            )
            config_entries_error = False

        # Lets check we got all the needed entries
        config_keys_OK = self.__check_config_keys()
        if config_keys_OK:
            config_entries_error = False
            self.run_log.debug(
                "The filename " +
                self.filename +
                " has all the required entries"
            )
        else:
            # Not all keys there
            config_entries_error = True
            self.run_log.warning(
                "The filename " +
                self.filename +
                " does not have all the required entries"
            )
            return config_entries_error

        # We pass all the keys. Lets granular check
        # Check the domain is a valid domian
        domain_OK = self.__check_FQDN(
            "anyhost",
            self.container['CONTAINER_DOMAIN_NAME']
        )
        if domain_OK:
            self.run_log.debug(
                "The domain " +
                self.container['CONTAINER_DOMAIN_NAME'] +
                " passes basic the check"
            )
        else:
            self.total_errors += 1
            self.run_log.warning(
                "The domain " +
                self.container['CONTAINER_DOMAIN_NAME'] +
                " does not pass the basic check"
            )
        # Lets check the container FQDN
        FQDN_container_OK = self.__check_FQDN(
            self.container['CONTAINER_HOSTNAME'],
            self.container['CONTAINER_DOMAIN_NAME']
        )
        if FQDN_container_OK:
            self.run_log.debug(
                "The container FQDN " +
                self.container['CONTAINER_HOSTNAME'] +
                '.' +
                self.container['CONTAINER_DOMAIN_NAME'] +
                " passes the basic check"
            )
        else:
            self.total_errors += 1
            self.run_log.warning(
                "The container FQDN " +
                self.container['CONTAINER_HOSTNAME'] +
                '.' +
                self.container['CONTAINER_DOMAIN_NAME'] +
                " does not pass the basic check"
            )

        CAMPUS_IP_OK = self.__check_IP(
            self.container['CAMPUS_INTERFACE_IP']
        )
        if CAMPUS_IP_OK:
            self.run_log.debug(
                "The CAMPUS IP " +
                self.container['CAMPUS_INTERFACE_IP'] +
                " passes the simple check"
            )
        else:
            self.total_errors += 1
            self.run_log.warning(
                "The CAMPUS IP " +
                self.container['CAMPUS_INTERFACE_IP'] +
                " does not pass the simple check"
            )
        # Now lets check that IP actually matches the reality
        self.run_log.debug(
            "Going to check if " +
            self.container['CAMPUS_INTERFACE_IP'] +
            " exists in this system"
        )
        if self.container['CAMPUS_INTERFACE_IP'] == self.CAMPUS_IPv4:
            self.run_log.debug(
                "The CAMPUS IP " +
                self.container['CAMPUS_INTERFACE_IP'] +
                " exists in this system"
            )
        else:
            self.total_errors += 1
            self.run_log.error(
                "The CAMPUS IP " +
                self.container['CAMPUS_INTERFACE_IP'] +
                " does not exist in this system"
            )
        RAS_IP_OK = self.__check_IP(
            self.container['RAS_INTERFACE_IP']
        )

        if RAS_IP_OK:
            self.run_log.debug(
                "The RAS IP " +
                self.container['RAS_INTERFACE_IP'] +
                " passes the simple check"
            )
        else:
            self.total_errors += 1
            self.run_log.warning(
                "The RAS IP " +
                self.container['RAS_INTERFACE_IP'] +
                " does not pass the simple check"
            )

        # Now lets check that IP actually matches the reality
        self.run_log.debug(
            "Going to check if " +
            self.container['RAS_INTERFACE_IP'] +
            " exists in this system"
        )
        if self.container['RAS_INTERFACE_IP'] == self.RAS_IPv4:
            self.run_log.debug(
                "The RAS IP " +
                self.container['RAS_INTERFACE_IP'] +
                " exists in this system"
            )
        else:
            self.total_errors += 1
            self.run_log.error(
                "The RAS IP " +
                self.container['RAS_INTERFACE_IP'] +
                " does not exist in this system"
            )


        # Recap errors
        if self.total_errors == 0:
            config_entries_error = False
            self.run_log.info(
                "All configurable variables checked passed"
            )
        else:
            config_entries_error = True
            self.run_log.error(
                "Not all entries on the file checks passed. " +
                "Please review the ERROR message[s] above this one"
            )

        return config_entries_error

    def __check_rcladmin_user(self):
        self.run_log.debug(
            "Going to check if this tool is been run with rcladmin user"
        )
        username = os.environ.get('USER') or os.environ.get('USERNAME')
        if username == "rcladmin":
            self.run_log.debug(
                "This tool is been run with rcladmin privileges"
            )
        else:
            self.run_log.error(
                "This tool is NOT to been run with rcladmin user"
            )
            self.run_log.debug(
                "Going to terminate with RC 15"
            )
            sys.exit(15)

    def prep_container(self):
        # Every start we check that not running already, if not running we delete the image
        contIsUp = self.__alreadyUP("rcl-official")
        if contIsUp:
            self.run_log.error(
                "We cannot start the RCL container as seems that is already UP."
            )
            self.run_log.debug(
                "Going to exit with RC=9"
            )
            sys.exit(9)
        else:
            self.run_log.debug(
                "Container is not UP, we will delete the image before start."
            )
            imgDeleted = self.__delete_image("rcl-official")
            if imgDeleted:
                self.run_log.debug(
                    "RCL image has been deleted, we continue."
                )
            else:
                self.run_log.error(
                    "Could not delete container image."
                )
                self.run_log.debug(
                    "Going to exit with RC=10"
                )
                sys.exit(10)
        # Users wants that we prep the container
        # This requires rclmgr -i, rclmgr -n
        self.run_log.debug(
            "Starting check if rclmgr exists"
        )
        file_exists = os.path.isfile("rclmgr")
        if file_exists:
            self.run_log.debug(
                "Completed check for rclmgr and exists"
            )
        else:
            self.run_log.debug(
                "Completed check for rclmgr and does not exist"
            )
            return False

        # Lets install the image, it might be there already
        image_file = None
        if self.IMAGE_TARBALL is not None:
            image_file = self.IMAGE_TARBALL
            self.run_log.debug(
                "Going to check if " +
                image_file +
                " exists"
            )
            image_file_OK = os.path.isfile(image_file)
            if image_file_OK:
                self.run_log.debug(
                    "The image file " +
                    image_file +
                    " exists"
                )
                self.run_log.info(
                    "Going to install " +
                    image_file +
                    ". Equivalent command is 'rclmgr -f " +
                    image_file +
                    " -i'"
                )
            # File does not exists
            else:
                self.run_log.error(
                    "The image file " +
                    image_file +
                    " does not exist"
                )
                return False

        # Lets use rclmgr install tools
        try:
            self.run_log.debug(
                "Going to import rclmgr"
            )
            import classes.rclmgr as rclmgr
            self.run_log.debug(
                "Imported rclmgr"
            )
        except ImportError:
            self.run_log.error(
                "Cannot import rclmgr"
            )
            self.run_log.debug(
                "Going to terminate with RC 22"
            )
            sys.exit(22)
        # We have rclmgr loaded now
        input0 = argparse.Namespace(
            config_file='rclmgr.yml',
            force=True,
            image_file_name=image_file,
            install=True,
            create_network=False,
            network_name="ess_network",
            run=False)
        self.run_log.debug(
            "Going to readconf with rclmgr"
        )
        try:
            rclmgr.readconf(input0)
            self.run_log.debug(
                "Success readconf with rclmgr"
            )
        except BaseException:
            self.run_log.error(
                "Could not readconf with rclmgr"
            )
            self.run_log.debug(
                "Going to terminate with RC 23"
            )
            sys.exit(23)
        self.run_log.info(
            "Going to install the image. It would do no changes if already installed."
        )
        try:
            self.run_log.debug(
                "Going to run rclmgr installimage"
            )
            if input0.image_file_name is not None:
                rclmgr.install_image_from_file(input0.image_file_name, input0.force)
            else:
                rclmgr.install_image_from_repo(input0.force)
            self.run_log.info(
                "Image has been installed succesfully."
            )
        except BaseException:
            err = sys.exc_info()[0]
            # We are back on error
            self.run_log.info(
                "Image installation has failed to install with " +
                str(err)
            )
            return False

        # We are this far it run OK
        return True

    def start_container(self):
        # Users wants that we run the container
        # We simulate rclmgr -r
        try:
            self.run_log.debug(
                "Going to import rclmgr"
            )
            import classes.rclmgr as rclmgr
            self.run_log.debug(
                "Imported essmgr"
            )
        except ImportError:
            self.run_log.error(
                "Cannot import essmgr"
            )
            self.run_log.debug(
                "Going to terminate with RC 22"
            )
            sys.exit(22)
        input0 = argparse.Namespace(
            config_file='rclmgr.yml',
            force=True,
            image_file_name=None,
            install=False,
            create_network=False,
            network_name="ess_network",
            run=True
            )
        self.run_log.debug(
            "Going to readconf with rclmgr"
        )
        try:
            rclmgr.readconf(input0)
            self.run_log.debug(
                "Success readconf with essmgr"
            )
        except BaseException:
            self.run_log.error(
                "Could not readconf with essmgr"
            )
            self.run_log.debug(
                "Going to terminate with RC 23"
            )
            sys.exit(23)
        self.run_log.info(
            "Going to start the container. On further runs use 'startRCLContainer' " +
            "command to manage this container"
        )

        try:
            self.run_log.debug(
                "Going to run rclmgr runcont"
            )
            rclmgr.run_container(input0, True)
        except BaseException:
            # We are back
            self.run_log.error(
                "The container run returned a non zero exit. " +
                "Please check the messages above. To start the " +
                "container again use 'startRCcont' again."
            )
            self.run_log.debug(
                "Going to terminate with RC 24"
            )
            sys.exit(24)
            return False  # This should never run
        self.run_log.debug(
            "We are back from rclmgr runcont normal mode"
        )
        return True

    def __podman_bin_exists(self):
        self.run_log.debug(
            "Going to check if podman binary exists"
        )
        podman_bin_OK = os.path.isfile('/bin/podman')
        if podman_bin_OK:
            self.run_log.debug(
                "podman binary exists"
            )
        else:
            self.run_log.error(
                "podman binary does not exists. We cannot continue"
            )
            self.run_log.debug(
                "Going to terminate with RC 26"
            )
            sys.exit(26)

    def __nmcli_bin_exists(self):
        self.run_log.debug(
            "Going to check if nmcli binary exists"
        )
        nmcli_bin_OK = os.path.isfile('/bin/nmcli')
        if nmcli_bin_OK:
            self.run_log.debug(
                "nmcli binary exists"
            )
        else:
            self.run_log.error(
                "nmcli binary does not exists. We cannot continue"
            )
            self.run_log.debug(
                "Going to terminate with RC 28"
            )
            sys.exit(28)

    def __SSR_SQL_check(self):
        # During SSR essutils  flow an SQL DB is created
        # We will use that to confirm SSR flow was indeed used
        # This is the first time we do this so warning and basic check
        sqlite3_DB_file = '/home/rcladmin/backup/essutils.sql'
        self.run_log.debug(
            "Going to check if SSR/essutils sqlite3 DB file exists"
        )
        sqlite3_DB_file_OK = os.path.isfile(sqlite3_DB_file)
        if sqlite3_DB_file_OK:
            self.run_log.debug(
                "SSR/essutils sqlite3 DB file exists"
            )
            try:
                db_conn = sqlite3.connect(sqlite3_DB_file)
                self.run_log.debug(
                    "Connected to sqlite3 DB file " +
                    sqlite3_DB_file
                )
            except BaseException:
                self.run_log.error(
                    "Cannot connect to sqlite3 DB file " +
                    sqlite3_DB_file
                )
                sys.exit(1)
            sql_c = db_conn.cursor()
            sql_ssrinitdate = '''SELECT task_date FROM SSR_TASKS WHERE task_name="DB_init";'''
            SSR_DBinit_date = sql_c.execute(sql_ssrinitdate).fetchone()[0]
            if SSR_DBinit_date == "":
                self.run_log.error(
                    "The SSR flow was most likely not run in this system."
                )
                self.run_log.debug(
                    "Going to terminate with RC 31"
                )
                sys.exit(31)
            else:
                self.run_log.debug(
                    "SSR/essutils tasks was started in this node on " +
                    SSR_DBinit_date
                )
        else:

            self.run_log.error(
                "SSR/essutils sqlite3 DB file does not exists. We cannot continue."
            )
            self.run_log.error(
                "The SSR flow was most likely not run in this system."
            )
            self.run_log.debug(
                "Going to terminate with RC 31"
            )
            sys.exit(31)

    def __check_RAS_IP(self):
        self.run_log.debug(
            "Going to check if IP address or RAS interface is the expected one"
        )
        is_in_netblock = self.__check_IP_in_netblock(self.RAS_IPv4, RAS_NETBLOCK)
        if is_in_netblock:
            self.run_log.debug(
                "Configured RAS IP " +
                str(self.RAS_IPv4) +
                " belongs to RAS netblock " +
                str(RAS_NETBLOCK)
            )
            if self.RAS_IPv4 == RAS_IP:
                self.run_log.debug(
                    "RAS IP is the expected one " +
                    RAS_IP
                )
            else:
                self.run_log.error(
                    "Configured RAS IP " +
                    str(self.RAS_IPv4) +
                    " is not " +
                    RAS_IP
                )
                self.run_log.debug(
                    "Going to exit with RC=7"
                )
                sys.exit(7)

        else:
            self.run_log.error(
                "Configured RAS IP " +
                str(self.RAS_IPv4) +
                " does not belong to RAS netblock " +
                str(RAS_NETBLOCK)
            )
            self.run_log.debug(
                "Going to exit with RC=7"
            )
            sys.exit(7)

    def __resolve_endpoints(self):
        self.run_log.debug(
            "Going to try to name resolve the IBM endpoints"
        )
        numberEndpoints = len(RCL_ENDPOINTS)
        resolvedEndpoints = 0
        for endpoint_name in RCL_ENDPOINTS:
            try:
                resolved_ip = socket.gethostbyname(endpoint_name)
                self.run_log.debug(
                    "The endpoint " +
                    endpoint_name +
                    " resolves to IP address " +
                    resolved_ip
                )
                resolvedEndpoints = resolvedEndpoints + 1
            except socket.gaierror:
                self.run_log.error(
                    "Could not resolve endpoint " +
                    endpoint_name
                )
            except BaseException:
                self.run_log.error(
                    "A generic error happened when tried to resolve " +
                    endpoint_name
                )
        if resolvedEndpoints == numberEndpoints:
            self.run_log.info(
                "All " +
                str(numberEndpoints) +
                " endpoint DNS names could be resolved"
            )
        else:
            self.run_log.error(
                "Not all " +
                str(numberEndpoints) +
                " endpoint DNS names could be resolved, we cannot continue"
            )
            self.run_log.debug(
                "Going to exit with RC=3"
            )
            sys.exit(3)

    def __reach_endpoints(self):
        self.run_log.debug(
            "Going to try to reach the IBM endpoints"
        )

        portToCheck=22
        reachedEndpoints = 0
        totalEndpoints = len(RCL_ENDPOINTS)
        for endpoint_name in RCL_ENDPOINTS:
            self.run_log.debug(
                "Going to open network socket"
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.run_log.debug(
                "Network socket is opened"
            )
            sock.settimeout(3)  # a 3 seconds timeout
            try:
                sock.connect((endpoint_name, portToCheck))
                self.run_log.debug(
                    "Connected to port " +
                    str(portToCheck) +
                    " at endpoint " +
                    endpoint_name
                )
                reachedEndpoints = reachedEndpoints + 1

                sock.close()
                self.run_log.debug(
                    "Network socket is closed"
                )
            # We already checked we can resolve
            except BaseException:
                self.run_log.warning(
                    "Could not reach port " +
                    str(portToCheck) +
                    " at endpoint " +
                    endpoint_name
                )
        if reachedEndpoints == totalEndpoints:
            self.run_log.info(
                "All " +
                str(totalEndpoints) +
                " endpoints can be reached on port " +
                str(portToCheck)
            )
        elif reachedEndpoints > 0 and reachedEndpoints < 4:
            self.run_log.warning(
                "Total " +
                str(reachedEndpoints) +
                " endpoints can be reached on port " +
                str(portToCheck)
            )
            self.run_log.warning(
                "Ideally all " + str(totalEndpoints) +
                " should be reachable for HA purpose on port " +
                str(portToCheck) + 
                ". Continuing..."
            )
        else:
            self.run_log.error(
                "Not any of " +
                str(totalEndpoints) +
                " IBM Service Portal Fornt server endpoints can be reached on port " +
                str(portToCheck)
            )
            self.run_log.error(
                "Looks like IBM Utility Host doesn't reach to public network."
            )
            self.run_log.error(
                "Public network connetivity should be avaiable on IBM Utility Host for Remote Code Load to work (use direct or proxy configuration)."
            )
            self.run_log.debug(
                "Going to exist with RC=6"
            )
            sys.exit(6)

    def __delete_image(self, img_str_find):

        images_list = self.__get_installed_containers()

        if len(images_list) == 0:
            self.run_log.info(
                "There are no images installed, none to be cleaned up"
            )
            return True
        else:
            self.run_log.debug(
                "There are images installed, proceeding further on clean up"
            )
        # Lets iterate the images looking for our img_str_find only
        image_ids_to_delete = []
        try:
            for image in images_list:
                if image['names'] is None:
                    self.run_log.debug(
                        "Detected image with no name we are not going to clean this one"
                    )
                    continue
                for image_alias_name in image['names']:
                    # It is supported to have more than 1
                    if img_str_find in image_alias_name:
                        self.run_log.info(
                            "Found image " +
                            image_alias_name +
                            " that we will try to delete"
                        )
                        short_id = image['id'][0:11]
                        long_id = image['id']
                        self.run_log.info(
                            "The image " +
                            image_alias_name +
                            " has long ID " +
                            long_id +
                            " and short ID " +
                            short_id
                        )
                        image_ids_to_delete.append(long_id)
                    else:
                        self.run_log.debug(
                            "Found image" +
                            image_alias_name +
                            " that we won't delete"
                        )
        except BaseException:
            self.run_log.debug(
                "There were some issues cleaning images, we can continue"
            )
        if len(image_ids_to_delete) == 0:
            self.run_log.info(
                "There are no images related to " +
                img_str_find +
                " to be deleted"
            )
            return True
        # We have at least 1 image ID to delete
        delete_issues = 0
        for image_id in set(image_ids_to_delete):
            try:
                self.run_log.info(
                    "Going to delete image with ID " +
                    image_id
                )
                delete_image_output = subprocess.check_output(
                    ["/bin/podman", "image", "rm", "--force", image_id],
                    stderr=subprocess.STDOUT
                ).strip().decode()
                self.run_log.info(
                    "Image with ID " +
                    image_id +
                    " deleted"
                )
            except BaseException:
                self.run_log.warn(
                    "Could not clean delete image with ID " +
                    image_id
                )
                try:
                    if delete_image_output != "":
                        self.run_log.warn(
                            "The output was: \n" +
                            delete_image_output
                        )
                except BaseException:
                    self.run_log.debug(
                        "We have no output from command"
                    )
                delete_issues += 1

        if delete_issues > 0:
            return False
        else:
            return True

    def __get_installed_containers(self):
        # Generates a JSON list of intalled containers
        self.run_log.debug(
            "Going to query the containers with podman ps command"
        )
        containers_json_output = subprocess.check_output(
            ["/bin/podman", "ps", "--all", "--format", "json"],
            stderr=subprocess.STDOUT
        ).strip().decode()
        self.run_log.debug(
            "Got back from querying containers with podman ps command"
        )
        self.run_log.debug(
            "Going to load containers JSON output into list"
        )
        try:
            container_list = json.loads(containers_json_output)
            self.run_log.debug(
                "Imported into a list the output from podman ps command"
            )
        except BaseException:
            self.run_log.debug(
                "Load of containers JSON returned and exception, " +
                "we consider no containers installed"
            )
            container_list = []
        return container_list

    def __alreadyUP(self, img_str_find):
        self.run_log.debug(
            "Method to reconnect to POD is called"
        )
        installedPODs = self.__get_installed_containers()
        # We might have more than one installed at this point
        isUP = False
        for pod in installedPODs:
            if pod['State'] == 3 or pod['State'] == "running":
                imageContUp = pod['Image']
                if pod['State'] == 3:
                    imageContUpID = pod['ID']
                else:
                    imageContUpID = pod['Id']
                self.run_log.debug(
                    "Found a POD with state = 3 (UP) " +
                    "and image " +
                    imageContUp +
                    " and ID " +
                    imageContUpID
                )
                if img_str_find in pod['Image']:
                    self.run_log.debug(
                        "Found the POD image we are looking for in UP."
                    )
                    isUP = True
                else:
                    self.run_log.debug(
                        "Although the POD image is UP, is not the one we are looking for."
                    )
            else:
                self.run_log.debug(
                    "Found installed container on other state than 3 (UP) " +
                    "and image " +
                    pod['Image']
                )
        return isUP