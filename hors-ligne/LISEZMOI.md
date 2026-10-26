# Dossier « hors-ligne » : éviter de télécharger

Le script `setup-windows.ps1` **cherche ici (et dans Téléchargements, Bureau, Documents et Dropbox) les fichiers déjà téléchargés**, et ne télécharge que ce qui manque. Idéal avec un forfait limité : quelqu'un télécharge les fichiers avec une bonne connexion, et te les envoie par **Dropbox ou clé USB**. Tu les mets dans ce dossier. C'est tout.

Pour voir ce qui serait téléchargé sur ton PC, double-clique sur `voir-les-telechargements.bat` (il n'installe rien).

## Les fichiers (tailles mesurées sur les sites officiels)

| Fichier à mettre ici | Taille | Où le télécharger (une seule fois) |
|---|---|---|
| `VirtualBox-7.2.22-175245-Win.exe` | 178 Mo | <https://download.virtualbox.org/virtualbox/7.2.22/VirtualBox-7.2.22-175245-Win.exe> |
| `vagrant_2.4.9_windows_amd64.msi` | 248 Mo | <https://releases.hashicorp.com/vagrant/2.4.9/vagrant_2.4.9_windows_amd64.msi> |
| `jammy-server-cloudimg-amd64-vagrant.box` (image Ubuntu 22.04) | 691 Mo | <https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64-vagrant.box> |
| `Git-…-64-bit.exe` (facultatif : inutile si tu télécharges le projet en ZIP) | environ 65 Mo | <https://git-scm.com/download/win> |

Les noms de fichiers ne doivent pas être changés (le script les reconnaît à leur nom). Une version plus récente de VirtualBox ou de Vagrant convient aussi.

Ce qui reste à télécharger quand même : les **paquets Ubuntu** (Snort, Suricata, Apache…), installés *dans* la machine virtuelle : environ 150 Mo (estimation). Pour ne rien télécharger du tout, voir « Exporter la machine » ci-dessous.

## Si tu as déjà des choses sur ton PC

- **VirtualBox ou Vagrant déjà installés** : détectés, jamais retéléchargés.
- **Une image Ubuntu déjà ajoutée à Vagrant** (`vagrant box list`) : réutilisée.
- **Une machine virtuelle Ubuntu déjà dans VirtualBox** (celle de ton projet) : le script te propose l'option la plus légère, installer le laboratoire directement dedans (environ 150 Mo, sans VirtualBox, Vagrant ni image à télécharger en plus).

## Exporter la machine : zéro téléchargement sur un autre PC

Sur un PC où le laboratoire est déjà installé, double-clique sur `setup-windows.ps1` avec l'action *Exporter* :

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1 -Action Exporter
```

Cela crée `harden-defense.box` (plus d'un Go), tout installé. Envoie-le par Dropbox ou clé USB : sur l'autre PC, mets-le dans ce dossier, lance `setup-windows.ps1`, le script l'utilise à la place de l'image Ubuntu et ne télécharge plus les paquets.
(Il ne réduit pas la taille du fichier à transférer, il évite seulement un téléchargement depuis internet.)

Les fichiers de ce dossier ne sont jamais envoyés sur GitHub (voir `.gitignore`).
