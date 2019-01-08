#!/bin/bash
easy_install pip
pip install flask
yum install httpd -y
iptables -A INPUT -p tcp -m multiport --dports 80,443,5000 -m conntrack --ctstate NEW,ESTABLISHED -j ACCEPT
iptables -A OUTPUT -p tcp -m multiport --dports 80,443,5000 -m conntrack --ctstate ESTABLISHED -j ACCEPT
cd /home/ec2-user
curl -O https://aws-codedeploy-eu-west-1.s3.amazonaws.com/latest/install
chmod +x ./install
./install auto
