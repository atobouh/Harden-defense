# Pour ceux qui n'ont PAS Ubuntu : une machine virtuelle Ubuntu se crée et se configure toute seule.
#
#   Windows : double-clique sur demarrer.bat  (ou : clic droit sur setup-windows.ps1 > Exécuter avec PowerShell)
#   Autres  : vagrant up    puis ouvre  http://localhost:5000
#             vagrant halt  pour éteindre,   vagrant destroy  pour tout effacer
#
# Le script setup-windows.ps1 installe VirtualBox et Vagrant à ta place. À la main, voir docs/installation.md.
#
# Économie de téléchargement : HD_BOX permet d'utiliser une image déjà présente sur le PC (voir docs/installation.md).
Vagrant.configure("2") do |config|
  # Image : celle choisie par setup-windows.ps1 (fichier .hd-box), sinon Ubuntu 22.04 officielle (≈ 690 Mo, téléchargée une seule fois).
  hd_box_file = File.join(File.dirname(__FILE__), ".hd-box")
  config.vm.box = ENV["HD_BOX"] || (File.exist?(hd_box_file) ? File.read(hd_box_file).strip : "ubuntu/jammy64")
  config.vm.box_check_update = false                          # pas de vérification réseau inutile
  config.vm.hostname = "harden-defense"
  config.vm.boot_timeout = 900                                # PC lent ou Hyper-V actif : on laisse 15 minutes
  config.ssh.insert_key = false                               # VM locale : permet d'exporter la machine (vagrant package)

  # Le dashboard de la VM s'ouvre sur TON navigateur, à l'adresse http://localhost:5000
  # (host_ip 127.0.0.1 : il n'est visible que depuis ton PC, pas depuis le réseau)
  config.vm.network "forwarded_port", guest: 5000, host: 5000, host_ip: "127.0.0.1", auto_correct: true

  config.vm.provider "virtualbox" do |vb|
    vb.name = "Harden Defense"
    vb.memory = 3072
    vb.cpus = 2
    vb.customize ["modifyvm", :id, "--uartmode1", "disconnected"]   # évite un fichier « console.log » dans le dossier du projet
  end

  # Dossier synchronisé : la VM n'y touche pas, elle en fait une copie propre avant d'installer.
  config.vm.synced_folder ".", "/vagrant", type: "virtualbox"

  # 10.0.2.2 = ton PC vu depuis la VM : il compte comme « la machine locale » pour modifier les réglages.
  # Le projet est copié avant l'installation, et les fins de ligne Windows (CRLF), qui cassent les scripts Linux, sont corrigées.
  # Si l'installation est interrompue (réseau, apt...), « vagrant up --provision » la reprend sans rien refaire de ce qui est fini.
  config.vm.provision "shell", privileged: true, env: { "HD_TRUSTED" => "10.0.2.2" }, inline: <<-SHELL
    if [ -f /var/lib/harden-defense/.installed ]; then echo "Laboratoire déjà installé : rien à refaire."; exit 0; fi
    set -e
    rm -rf /home/vagrant/hd-src && mkdir -p /home/vagrant/hd-src
    (cd /vagrant && tar --exclude=.git --exclude=.vagrant --exclude=docs --exclude=hors-ligne --exclude='*.box' -cf - .) | tar -xf - -C /home/vagrant/hd-src
    find /home/vagrant/hd-src -type f \\( -name '*.sh' -o -name harden -o -name '*.service' -o -name '*.conf' -o -name '*.py' -o -name '*.rules' -o -name '*.txt' \\) -exec sed -i 's/\\r$//' {} +
    bash /home/vagrant/hd-src/install.sh
  SHELL
end
