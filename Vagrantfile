# coding: utf-8
# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version.
VAGRANTFILE_API_VERSION = "2"
Vagrant.require_version ">=1.7.0"

$bootstrap_ubuntu = <<SCRIPT
# apt-get update && sudo apt-get -y upgrade && sudo apt-get -y dist-upgrade
apt update
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt install -y python3.7 python3.7-venv
ln -sf python3.7 /usr/bin/python3

SCRIPT

$install_mosquitto = <<SCRIPT
apt install -y mosquitto mosquitto-clients

cat <<EOT > /etc/mosquitto/conf.d/localbroker.conf
allow_anonymous true
bind_address 192.168.123.123
EOT

systemctl enable --now mosquitto
systemctl status --full --no-pager mosquitto
SCRIPT

$install_mqtt2kasa = <<SCRIPT
rm -rf /vagrant/env
/vagrant/mqtt2kasa/bin/create-env.sh
source /vagrant/env/bin/activate
pip install --upgrade pip
echo '[ -e /vagrant/env/bin/activate ] && source /vagrant/env/bin/activate' >> ~/.bashrc

ln -s /vagrant/data/config.yaml.vagrant ~/mqtt2kasa.config.yaml
sudo cp -v /vagrant/mqtt2kasa/bin/mqtt2kasa.service.vagrant /lib/systemd/system/mqtt2kasa.service
sudo systemctl enable --now mqtt2kasa.service

ln -s /vagrant/mqtt2kasa/bin/tail_log.sh ~/
ln -s /vagrant/mqtt2kasa/bin/reload_config.sh ~/
ln -s /vagrant/mqtt2kasa/tests/basic_test.sh.vagrant ~/basic_test.sh
SCRIPT

$test_mqtt2kasa = <<SCRIPT
[ -d 'tplink-smarthome-simulator' ] || {
    pushd ~/
    sudo apt install -y nodejs npm git
    git clone https://github.com/flavio-fernandes/tplink-smarthome-simulator.git
    cd tplink-smarthome-simulator
    npm install
    # Add secondary ips to satisfy simulator.js
    for x in {201..204}; do
        sudo ip a add 192.168.123.${x}/32 dev eth1
    done
    cp -v /vagrant/mqtt2kasa/tests/simulator.js.vagrant ./test/simulator.js
    sudo cp -v /vagrant/mqtt2kasa/tests/tplink-smarthome-simulator.service.vagrant \
               /lib/systemd/system/tplink-smarthome-simulator.service
    sudo systemctl enable --now tplink-smarthome-simulator.service
    sudo systemctl status --full --no-pager tplink-smarthome-simulator

    # sudo journalctl --unit tplink-smarthome-simulator --since today --follow
    # sudo journalctl --unit mqtt2kasa --since today --follow
    popd
}

# sudo systemctl restart tplink-smarthome-simulator.service
sudo systemctl status --full --no-pager mqtt2kasa
sleep 5  ; # give it a few secs for service to start
~/basic_test.sh
SCRIPT


Vagrant.configure(2) do |config|

    vm_memory = ENV['VM_MEMORY'] || '512'
    vm_cpus = ENV['VM_CPUS'] || '2'

    config.vm.hostname = "mqtt2kasaVM"
    config.vm.box = "roboxes/ubuntu2004"
    config.vm.box_check_update = false

    # config.vm.synced_folder "#{ENV['PWD']}", "/vagrant", sshfs_opts_append: "-o nonempty", disabled: false, type: "sshfs"
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
