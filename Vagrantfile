# coding: utf-8
# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version.
VAGRANTFILE_API_VERSION = "2"
Vagrant.require_version ">=1.7.0"

$bootstrap_ubuntu = <<SCRIPT
set -o errexit
export DEBIAN_FRONTEND=noninteractive

# The box ships systemd-resolved with DNSSEC=yes (strict). Validating the
# archive mirror's CNAME chain fails with "missing-key", so every lookup
# through the 127.0.0.53 stub fails and apt-get retries forever, logging
# "Tried to start delayed item ... but failed" until the provisioner is
# killed. Relax it to the Ubuntu default before anything needs the network.
mkdir -p /etc/systemd/resolved.conf.d
cat <<EOT > /etc/systemd/resolved.conf.d/99-vagrant-dnssec.conf
[Resolve]
DNSSEC=no
EOT
systemctl restart systemd-resolved

# Wait for the stub resolver to answer again before handing apt the network.
apt_mirror_host=$(awk '/^deb /{print $2}' /etc/apt/sources.list | head -1 | awk -F/ '{print $3}')
apt_mirror_host=${apt_mirror_host:-archive.ubuntu.com}
for _ in $(seq 30); do
    getent hosts "${apt_mirror_host}" > /dev/null 2>&1 && break
    sleep 1
done
getent hosts "${apt_mirror_host}"

# Give up instead of spinning forever when the mirror is unreachable.
cat <<EOT > /etc/apt/apt.conf.d/99-vagrant-retries
Acquire::Retries "3";
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
EOT

# apt-get update && sudo apt-get -y upgrade && sudo apt-get -y dist-upgrade
apt-get update
apt-get install -y software-properties-common
# Use native Python 3 available in ubuntu-latest
apt-get install -y python3-venv python3-pip

SCRIPT

$install_mosquitto = <<SCRIPT
set -o errexit
export DEBIAN_FRONTEND=noninteractive
apt-get install -y mosquitto mosquitto-clients

cat <<EOT > /etc/mosquitto/conf.d/localbroker.conf
allow_anonymous true
# listener 1883 192.168.123.123
listener 1883 0.0.0.0
log_type all
log_dest stdout
EOT

systemctl enable mosquitto
systemctl restart mosquitto
systemctl status --full --no-pager mosquitto || true
SCRIPT

$install_mqtt2kasa = <<SCRIPT
set -o errexit
rm -rf /vagrant/env
/vagrant/mqtt2kasa/bin/create-env.sh
source /vagrant/env/bin/activate
pip install --upgrade pip
grep -qF '/vagrant/env/bin/activate' ~/.bashrc || \
    echo '[ -e /vagrant/env/bin/activate ] && source /vagrant/env/bin/activate' >> ~/.bashrc

ln -sfn /vagrant/data/config.yaml.vagrant ~/mqtt2kasa.config.yaml
sudo cp -v /vagrant/mqtt2kasa/bin/mqtt2kasa.service.vagrant /lib/systemd/system/mqtt2kasa.service
sudo systemctl enable --now mqtt2kasa.service

ln -sfn /vagrant/mqtt2kasa/bin/tail_log.sh ~/tail_log.sh
ln -sfn /vagrant/mqtt2kasa/bin/reload_config.sh ~/reload_config.sh
ln -sfn /vagrant/mqtt2kasa/tests/basic_test.sh.vagrant ~/basic_test.sh
SCRIPT

$test_mqtt2kasa = <<SCRIPT
set -o errexit
[ -d 'tplink-smarthome-simulator' ] || {
    pushd ~/
    export DEBIAN_FRONTEND=noninteractive
    sudo apt-get install -y nodejs npm git
    git clone https://github.com/flavio-fernandes/tplink-smarthome-simulator.git
    cd tplink-smarthome-simulator
    npm install

    # Add secondary IPs configuration via Netplan
    echo "network:
      version: 2
      renderer: networkd
      ethernets:
        eth1:
          addresses:
            - 192.168.123.201/32
            - 192.168.123.202/32
            - 192.168.123.203/32
            - 192.168.123.204/32
    " | sudo tee /etc/netplan/02-secondary-ips.yaml > /dev/null
    sudo chmod 600 /etc/netplan/02-secondary-ips.yaml
    sudo netplan apply

    cp -v /vagrant/mqtt2kasa/tests/simulator.js.vagrant ./test/simulator.js
    sudo cp -v /vagrant/mqtt2kasa/tests/tplink-smarthome-simulator.service.vagrant \
               /lib/systemd/system/tplink-smarthome-simulator.service
    sudo systemctl enable --now tplink-smarthome-simulator.service
    sudo systemctl status --full --no-pager tplink-smarthome-simulator || true

    # sudo journalctl --unit tplink-smarthome-simulator --since today --follow
    # sudo journalctl --unit mqtt2kasa --since today --follow
    # sudo journalctl --unit mosquitto --since today --follow
    popd
}

# sudo systemctl restart tplink-smarthome-simulator.service
sudo systemctl status --full --no-pager mqtt2kasa || true
sleep 5  ; # give it a few secs for service to start
pushd /vagrant
source /vagrant/env/bin/activate
pip install pytest
python -m pytest mqtt2kasa/tests/unit
popd
~/basic_test.sh
SCRIPT


Vagrant.configure(2) do |config|

    vm_memory = ENV['VM_MEMORY'] || '2048'
    vm_cpus = ENV['VM_CPUS'] || '2'

    config.vm.hostname = "mqtt2kasaVM"
    config.vm.box = "generic/ubuntu2204"
    config.vm.box_check_update = false

    # config.vm.synced_folder "#{ENV['PWD']}", "/vagrant", disabled: false, type: "sshfs"
    # Optional: Uncomment line above and comment out the line below if you have
    # the vagrant sshfs plugin and would like to mount the directory using sshfs.
    config.vm.synced_folder ".", "/vagrant", type: "rsync"

    config.vm.network 'private_network', ip: "192.168.123.123"

    config.vm.provision "bootstrap_ubuntu", type: "shell", inline: $bootstrap_ubuntu
    config.vm.provision "install_mosquitto", type: "shell", inline: $install_mosquitto
    config.vm.provision "install_mqtt2kasa", type: "shell", inline: $install_mqtt2kasa, privileged: false
    config.vm.provision "test_mqtt2kasa", type: "shell", inline: $test_mqtt2kasa, privileged: false

    config.vm.provider 'libvirt' do |lb|
        lb.nested = true
        lb.memory = vm_memory
        lb.cpus = vm_cpus
        lb.suspend_mode = 'managedsave'
        #lb.storage_pool_name = 'images'
    end
    config.vm.provider "virtualbox" do |vb|
       vb.memory = vm_memory
       vb.cpus = vm_cpus
       vb.customize ["modifyvm", :id, "--nested-hw-virt", "on"]
       vb.customize ["modifyvm", :id, "--nictype1", "virtio"]
       vb.customize [
           "guestproperty", "set", :id,
           "/VirtualBox/GuestAdd/VBoxService/--timesync-set-threshold", 10000
          ]
    end
end
