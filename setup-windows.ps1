<#
  Harden Defense : installation automatique sur Windows 10 / 11 (PC Intel ou AMD).

  Lancement : clic droit sur ce fichier > "Exécuter avec PowerShell"
          ou : double-clic sur  demarrer.bat
          ou, dans PowerShell : powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1

  Ce que fait ce script (tu n'as rien d'autre à faire) :
    1. te montre ce qui sera téléchargé (et réutilise tout ce qui est déjà sur ton PC) ;
    2. vérifie que ton PC peut faire tourner une machine virtuelle ;
    3. installe VirtualBox, Vagrant et git s'ils manquent ;
    4. crée la machine virtuelle Ubuntu qui contient tout le laboratoire (Vagrantfile) ;
    5. ouvre le dashboard : http://localhost:5000

  Il peut être relancé autant de fois que nécessaire : il reprend là où il s'était arrêté.

  Actions : Installer (par défaut) | Demarrer | Arreter | Desinstaller | Exporter
  Options : -PlanSeulement   montre ce qui serait téléchargé, sans rien installer
            -Local DOSSIER   dossier où chercher des fichiers déjà téléchargés (Dropbox, clé USB...)
            -DesactiverHyperV  (voir le message d'aide si VirtualBox est très lent)
#>
[CmdletBinding()]
param(
    [ValidateSet('Installer', 'Demarrer', 'Arreter', 'Desinstaller', 'Exporter')]
    [string]$Action = 'Installer',
    [switch]$PlanSeulement,
    [string]$Local = '',
    [switch]$DesactiverHyperV,
    [switch]$SansPause
)

# On gère nous-mêmes les erreurs des programmes externes (winget, vagrant...) : on lit leur code de retour.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# Tailles (en Mo) des téléchargements, mesurées sur les sites officiels. Sert à prévenir AVANT de télécharger.
$Taille = @{ VirtualBox = 178; Vagrant = 248; Git = 65; ImageUbuntu = 691; PaquetsUbuntu = 150 }
$BoiteUbuntu = 'ubuntu/jammy64'
$BoiteLabo = 'harden/defense'

# ----------------------------------------------------------------------------------------------
# Outils d'affichage et de journal
# ----------------------------------------------------------------------------------------------
$Script:Journal = Join-Path $env:TEMP 'harden-defense-setup.log'
$Script:Etape = 0
$Script:EtapesTotal = 6
$Script:Racine = if ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { (Get-Location).Path }

function Ecrire-Journal([string]$Texte) {
    try { Add-Content -Path $Script:Journal -Value ("{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $Texte) -Encoding UTF8 } catch { }
}
function Dire([string]$Texte, [string]$Couleur = 'Gray') { Write-Host $Texte -ForegroundColor $Couleur; Ecrire-Journal $Texte }
function Etape([string]$Titre) {
    $Script:Etape++
    Write-Host ''
    Write-Host ("[{0}/{1}] {2}" -f $Script:Etape, $Script:EtapesTotal, $Titre) -ForegroundColor Cyan
    Ecrire-Journal ("=== [{0}/{1}] {2}" -f $Script:Etape, $Script:EtapesTotal, $Titre)
}
function Ok([string]$Texte) { Dire ("    OK  " + $Texte) 'Green' }
function Info([string]$Texte) { Dire ("    " + $Texte) 'Gray' }
function Avertir([string]$Texte) { Dire ("    /!\ " + $Texte) 'Yellow' }

function Mo([double]$Valeur) {
    if ($Valeur -ge 1024) { return ((($Valeur / 1024).ToString('0.0', [Globalization.CultureInfo]::InvariantCulture)) -replace '\.', ',') + ' Go' }
    return ('{0:0} Mo' -f $Valeur)
}

function Attendre-Fin {
    if ($SansPause) { return }
    Write-Host ''
    try { Read-Host "Appuie sur Entrée pour fermer cette fenêtre" | Out-Null } catch { }
}

function Arreter-Proprement([string]$Titre, [string[]]$Lignes, [int]$Code = 1) {
    Write-Host ''
    Write-Host ("  X  " + $Titre) -ForegroundColor Red
    foreach ($l in $Lignes) { Write-Host ("     " + $l) -ForegroundColor Yellow }
    Ecrire-Journal ("ARRET : " + $Titre)
    Write-Host ''
    Write-Host ("     Journal complet : " + $Script:Journal) -ForegroundColor DarkGray
    Attendre-Fin
    exit $Code
}

function Montrer-Fin-Du-Journal {
    Write-Host ''
    Write-Host '     Les dernières lignes du journal :' -ForegroundColor DarkGray
    try {
        Get-Content -Path $Script:Journal -Tail 25 -ErrorAction Stop | ForEach-Object { Write-Host ("       " + $_) -ForegroundColor DarkGray }
    } catch { }
    Write-Host ("     Journal complet : " + $Script:Journal) -ForegroundColor DarkGray
}

# ----------------------------------------------------------------------------------------------
# Ce qui est déjà sur le PC (rien n'est retéléchargé si on peut l'éviter)
# ----------------------------------------------------------------------------------------------
function Actualiser-Chemin {
    # Après une installation, la fenêtre en cours ne connaît pas encore les nouveaux programmes : on relit le PATH de Windows.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = ($machine + ';' + $user)
}

function Trouver-Programme([string]$Nom, [string[]]$Emplacements) {
    $cmd = Get-Command $Nom -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    foreach ($e in $Emplacements) { if (Test-Path -LiteralPath $e) { return $e } }
    return $null
}
function Chercher-VBoxManage { Trouver-Programme 'VBoxManage.exe' @("$env:ProgramFiles\Oracle\VirtualBox\VBoxManage.exe") }
function Chercher-Vagrant { Trouver-Programme 'vagrant.exe' @('C:\HashiCorp\Vagrant\bin\vagrant.exe', "$env:ProgramFiles\Vagrant\bin\vagrant.exe") }
function Chercher-Git { Trouver-Programme 'git.exe' @("$env:ProgramFiles\Git\cmd\git.exe", "${env:ProgramFiles(x86)}\Git\cmd\git.exe") }

function Dossiers-De-Recherche {
    # Les endroits où l'on cherche des fichiers déjà téléchargés (Dropbox, Téléchargements, clé USB copiée dans « hors-ligne »...).
    $liste = @()
    if ($Local) { $liste += $Local }
    $liste += (Join-Path $Script:Racine 'hors-ligne')
    $liste += $Script:Racine
    foreach ($sous in @('Downloads', 'Desktop', 'Documents', 'Dropbox', 'Dropbox\hors-ligne', 'OneDrive\Documents')) { $liste += (Join-Path $env:USERPROFILE $sous) }
    return ($liste | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique)
}

function Trouver-Fichier-Local([string[]]$Motifs, [double]$TailleMinMo = 0) {
    foreach ($dossier in (Dossiers-De-Recherche)) {
        foreach ($motif in $Motifs) {
            $f = Get-ChildItem -LiteralPath $dossier -Filter $motif -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Length -ge ($TailleMinMo * 1048576) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($f) { return $f.FullName }
        }
    }
    return $null
}

function Boite-Deja-Ajoutee([string]$Vagrant) {
    if (-not $Vagrant) { return $null }
    $liste = (& $Vagrant box list 2>&1) -join "`n"
    if ($liste -match [regex]::Escape($BoiteLabo)) { return $BoiteLabo }
    if ($liste -match [regex]::Escape($BoiteUbuntu)) { return $BoiteUbuntu }
    return $null
}

function Calculer-Plan {
    # Retourne ce qui est présent, ce qui est trouvé sur le PC, et ce qu'il faudra télécharger.
    Actualiser-Chemin
    $vbox = Chercher-VBoxManage
    $vag = Chercher-Vagrant
    $git = Chercher-Git
    $aGit = $git -or (Test-Path -LiteralPath (Join-Path $Script:Racine 'Vagrantfile'))
    $p = [ordered]@{}
    $p.VirtualBox = @{ Nom = 'VirtualBox'; Present = [bool]$vbox; Fichier = $null; Mo = $Taille.VirtualBox }
    $p.Vagrant = @{ Nom = 'Vagrant'; Present = [bool]$vag; Fichier = $null; Mo = $Taille.Vagrant }
    $p.Git = @{ Nom = 'git'; Present = [bool]$aGit; Fichier = $null; Mo = $Taille.Git }
    if (-not $p.VirtualBox.Present) { $p.VirtualBox.Fichier = Trouver-Fichier-Local @('VirtualBox-*-Win.exe') 50 }
    if (-not $p.Vagrant.Present) { $p.Vagrant.Fichier = Trouver-Fichier-Local @('vagrant_*_windows_amd64.msi') 50 }
    if (-not $p.Git.Present) { $p.Git.Fichier = Trouver-Fichier-Local @('Git-*-64-bit.exe') 20 }

    $deja = Boite-Deja-Ajoutee $vag
    $boiteLocale = $null
    $nomBoite = $BoiteUbuntu
    $moImage = $Taille.ImageUbuntu
    $paquets = $Taille.PaquetsUbuntu
    if ($deja) {
        $moImage = 0
        $nomBoite = $deja
    } else {
        $baked = Trouver-Fichier-Local @('harden-defense*.box') 300
        if ($baked) { $boiteLocale = $baked; $nomBoite = $BoiteLabo; $moImage = 0; $paquets = 0 }
        else {
            $ubuntu = Trouver-Fichier-Local @('*jammy*.box', 'ubuntu*.box') 300
            if ($ubuntu) { $boiteLocale = $ubuntu; $moImage = 0 }
        }
    }
    if ($deja -eq $BoiteLabo) { $paquets = 0 }
    $p.Image = @{ Nom = "Image Ubuntu ($nomBoite)"; Present = [bool]$deja; Fichier = $boiteLocale; Mo = $moImage; Taille = $Taille.ImageUbuntu; NomBoite = $nomBoite }
    $p.Paquets = @{ Nom = 'Paquets Ubuntu (Snort, Suricata, Apache...)'; Present = ($paquets -eq 0); Fichier = $null; Mo = $paquets; Taille = $Taille.PaquetsUbuntu }
    return $p
}

function Afficher-Plan($plan) {
    Write-Host ''
    Write-Host '  Ce qui sera téléchargé (seulement ce qui manque) :' -ForegroundColor White
    $total = 0.0
    foreach ($cle in $plan.Keys) {
        $e = $plan[$cle]
        if ($e.Present) {
            $etat = 'déjà là, rien à télécharger'; $couleur = 'Green'
        } elseif ($e.Fichier) {
            $etat = 'trouvé sur ton PC, rien à télécharger : ' + (Split-Path -Leaf $e.Fichier); $couleur = 'Green'
        } else {
            $aTelecharger = if ($e.Taille) { $e.Taille } else { $e.Mo }
            $total += [double]$aTelecharger
            $etat = 'à télécharger : environ ' + (Mo $aTelecharger); $couleur = 'Yellow'
        }
        Write-Host ('    {0,-44} {1}' -f $e.Nom, $etat) -ForegroundColor $couleur
    }
    Write-Host ''
    if ($total -gt 0) { Write-Host ('  Total à télécharger : environ ' + (Mo $total)) -ForegroundColor White } else { Write-Host '  Total à télécharger : presque rien.' -ForegroundColor Green }
    Write-Host '  Astuce forfait limité : branche-toi en Wi-Fi / Ethernet illimité, ou récupère les fichiers avec Dropbox ou une clé USB' -ForegroundColor DarkGray
    Write-Host '  et mets-les dans le dossier « hors-ligne » du projet (voir hors-ligne\LISEZMOI.md) : le script les utilise tout seul.' -ForegroundColor DarkGray
    Ecrire-Journal ("Plan : total {0} Mo" -f $total)
}

function Trouver-Vm-Ubuntu {
    $vbox = Chercher-VBoxManage
    if (-not $vbox) { return $null }
    $vms = & $vbox list vms 2>$null
    foreach ($l in $vms) { if ($l -match '^"([^"]*ubuntu[^"]*)"' -and $l -notmatch 'Harden Defense') { return $Matches[1] } }
    return $null
}

# ----------------------------------------------------------------------------------------------
# « -PlanSeulement » : on montre le plan et on s'arrête (aucun droit administrateur nécessaire)
# ----------------------------------------------------------------------------------------------
if ($PlanSeulement) {
    Write-Host ''
    Write-Host '  Harden Defense : ce que l''installation va télécharger' -ForegroundColor White
    Afficher-Plan (Calculer-Plan)
    $vm = Trouver-Vm-Ubuntu
    if ($vm) { Write-Host ("`n  Tu as déjà une machine virtuelle Ubuntu (« {0} ») : option encore plus légère (environ {1} à télécharger), voir le guide." -f $vm, (Mo $Taille.PaquetsUbuntu)) -ForegroundColor Cyan }
    Attendre-Fin
    exit 0
}

# ----------------------------------------------------------------------------------------------
# 0. Administrateur : on se relance tout seul (fenêtre « Contrôle de compte d'utilisateur »)
# ----------------------------------------------------------------------------------------------
$estAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $estAdmin) {
    if (-not $PSCommandPath) {
        Write-Host "Enregistre d'abord ce fichier sur ton PC (clic droit > Enregistrer sous), puis lance-le avec un clic droit > Exécuter avec PowerShell." -ForegroundColor Yellow
        Attendre-Fin
        exit 1
    }
    Write-Host "Windows va te demander l'autorisation de continuer : clique sur « Oui »." -ForegroundColor Cyan
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-Action', $Action)
    if ($Local) { $arguments += @('-Local', ('"{0}"' -f $Local)) }
    if ($DesactiverHyperV) { $arguments += '-DesactiverHyperV' }
    if ($SansPause) { $arguments += '-SansPause' }
    try {
        Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -Verb RunAs -ErrorAction Stop
    } catch {
        Write-Host "L'autorisation a été refusée : l'installation a besoin des droits administrateur pour installer VirtualBox." -ForegroundColor Yellow
        Write-Host "Relance le script et clique sur « Oui » dans la fenêtre de Windows." -ForegroundColor Yellow
        Attendre-Fin
        exit 1
    }
    exit 0
}

# À partir d'ici nous sommes administrateur.
Set-Location -Path $Script:Racine
"" | Set-Content -Path $Script:Journal -Encoding UTF8
Ecrire-Journal ("Harden Defense - setup-windows.ps1 - action {0} - {1}" -f $Action, (Get-Date))
$env:VAGRANT_DEFAULT_PROVIDER = 'virtualbox'
$env:VAGRANT_CHECKPOINT_DISABLE = '1'
$env:VAGRANT_NO_COLOR = '1'

Write-Host ''
Write-Host '  Harden Defense : installation automatique pour Windows' -ForegroundColor White
Write-Host '  (la première fois : 25 à 40 minutes, surtout du téléchargement. Tu peux faire autre chose pendant ce temps.)' -ForegroundColor DarkGray

# ----------------------------------------------------------------------------------------------
# Vérifications du PC
# ----------------------------------------------------------------------------------------------
function Redemarrage-En-Attente {
    $cles = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
    )
    foreach ($c in $cles) { if (Test-Path -LiteralPath $c) { return $true } }
    return $false
}

function Verifier-Pc {
    Etape 'Vérification de ton ordinateur'
    $os = Get-CimInstance Win32_OperatingSystem
    $build = [int]$os.BuildNumber
    Info ("Windows : {0} (version {1})" -f $os.Caption, $os.Version)
    if ($build -lt 17763) {
        Arreter-Proprement 'Cette version de Windows est trop ancienne.' @(
            'Il faut Windows 10 (version 1809 ou plus récente) ou Windows 11.',
            'Lance Windows Update pour mettre ton PC à jour, puis relance ce script.')
    }

    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    if ($cpu.Architecture -eq 12 -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        Arreter-Proprement 'Ce PC a un processeur ARM (Windows sur ARM).' @(
            "VirtualBox ne fonctionne pas sur les processeurs ARM : l'installation automatique est impossible.",
            "Il faut un PC avec un processeur Intel ou AMD (la grande majorité des PC).")
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        Arreter-Proprement 'Ce Windows est en 32 bits.' @('Il faut un Windows 64 bits pour VirtualBox.')
    }

    # Mémoire et disque : on prévient, on ne bloque que si c'est vraiment trop juste.
    $ramGo = [math]::Round($os.TotalVisibleMemorySize / 1048576, 1)
    Info ("Mémoire : {0} Go" -f $ramGo)
    if ($ramGo -lt 6) {
        Arreter-Proprement 'Pas assez de mémoire (RAM).' @(
            ("Ton PC a {0} Go. La machine virtuelle en utilise 3 : il en faut au moins 8 au total." -f $ramGo),
            'Ferme les autres programmes ou utilise un PC plus récent.')
    } elseif ($ramGo -lt 7.5) {
        Avertir 'Peu de mémoire : ferme ton navigateur et les gros programmes pendant l''installation.'
    }
    try {
        $lecteur = (Split-Path -Qualifier $Script:Racine)
        $libre = [math]::Round((Get-PSDrive -Name $lecteur.TrimEnd(':') -ErrorAction Stop).Free / 1073741824, 1)
        Info ("Espace disque libre sur {0} : {1} Go" -f $lecteur, $libre)
        if ($libre -lt 15) {
            Arreter-Proprement 'Pas assez de place sur le disque.' @(("Il reste {0} Go sur {1}. Il en faut au moins 15." -f $libre, $lecteur), 'Libère de la place (Paramètres > Système > Stockage) puis relance le script.')
        }
    } catch { }

    # Virtualisation activée dans le BIOS ?
    $cs = Get-CimInstance Win32_ComputerSystem
    $hyperviseur = [bool]$cs.HypervisorPresent
    $vt = $cpu.VirtualizationFirmwareEnabled
    Ecrire-Journal ("VirtualizationFirmwareEnabled={0} HypervisorPresent={1}" -f $vt, $hyperviseur)
    if ($hyperviseur) {
        # Si Windows fait tourner son propre hyperviseur, la virtualisation est forcément active (le BIOS est bon).
        Ok 'Virtualisation matérielle : active'
    } elseif ($vt -eq $true) {
        Ok 'Virtualisation matérielle : activée dans le BIOS'
    } elseif ($vt -eq $false) {
        Arreter-Proprement 'La virtualisation est désactivée dans le BIOS de ton PC.' @(
            "C'est un réglage du PC (pas de Windows). Il faut l'activer une seule fois :",
            '',
            '  1. Redémarre le PC et appuie plusieurs fois sur la touche du BIOS dès l''écran noir de démarrage',
            '     (selon la marque : F2, Suppr, F10, F12 ou Échap).',
            '     Astuce Windows 11/10 : Paramètres > Système > Récupération > Démarrage avancé > Redémarrer maintenant,',
            '     puis Dépannage > Options avancées > Paramètres du micrologiciel UEFI.',
            '     Autre astuce : tape  shutdown /r /fw /t 0  dans PowerShell (administrateur).',
            '  2. Cherche une option nommée :',
            '       - Intel : « Intel Virtualization Technology », « VT-x » ou « Virtualization Technology »',
            '       - AMD   : « SVM Mode », « AMD-V » ou « Virtualization »',
            '     (souvent dans Advanced, Configuration, CPU ou Security).',
            '  3. Mets-la sur « Enabled » (activé), enregistre avec F10, le PC redémarre.',
            '  4. Relance ce script.')
    } else {
        Avertir 'Impossible de lire l''état de la virtualisation (machine virtuelle ou PC particulier) : on continue.'
    }
    return @{ Hyperviseur = $hyperviseur; RamGo = $ramGo }
}

function Etat-HyperV {
    # Hyper-V, « Plateforme de machine virtuelle » (WSL2), « Plateforme d'hyperviseur Windows », Intégrité de la mémoire...
    $actifs = New-Object System.Collections.Generic.List[string]
    foreach ($f in @(
            @('Microsoft-Hyper-V-All', 'Hyper-V'),
            @('VirtualMachinePlatform', 'Plateforme de machine virtuelle (utilisée par WSL2)'),
            @('HypervisorPlatform', "Plateforme d'hyperviseur Windows"),
            @('Microsoft-Windows-Subsystem-Linux', 'Sous-système Windows pour Linux (WSL)'))) {
        try {
            $e = Get-WindowsOptionalFeature -Online -FeatureName $f[0] -ErrorAction Stop
            if ($e.State -eq 'Enabled') { $actifs.Add($f[1]) }
        } catch { }
    }
    try {
        $dg = Get-CimInstance -ClassName Win32_DeviceGuard -Namespace 'root\Microsoft\Windows\DeviceGuard' -ErrorAction Stop
        if ($dg.VirtualizationBasedSecurityStatus -eq 2) { $actifs.Add("Isolation du noyau / Intégrité de la mémoire (sécurité Windows)") }
    } catch { }
    return $actifs
}

function Gerer-HyperV($pc) {
    Etape 'Compatibilité avec Hyper-V / WSL2'
    $actifs = Etat-HyperV
    $enMarche = $pc.Hyperviseur
    if ($actifs.Count -gt 0) { Info ("Fonctionnalités Windows de virtualisation actives : " + ($actifs -join ' ; ')) }

    if ($DesactiverHyperV) {
        & bcdedit.exe /set hypervisorlaunchtype off | Out-Null
        Ecrire-Journal ("bcdedit hypervisorlaunchtype off -> code {0}" -f $LASTEXITCODE)
        Arreter-Proprement 'Hyper-V sera désactivé au prochain démarrage de Windows.' @(
            'Redémarre le PC, puis relance ce script : VirtualBox sera rapide.',
            "Pour réactiver Hyper-V / WSL2 / Docker plus tard :  bcdedit /set hypervisorlaunchtype auto  (puis redémarrer).") 0
    }

    if ($enMarche) {
        Avertir "Windows fait déjà tourner son propre hyperviseur (Hyper-V, WSL2 ou « Intégrité de la mémoire »)."
        Info 'VirtualBox 7 sait fonctionner à côté, mais la machine virtuelle sera PLUS LENTE (le laboratoire reste utilisable).'
        Info "Si le démarrage échoue ou est très lent, relance avec la désactivation d'Hyper-V :"
        Info '    powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1 -DesactiverHyperV'
        Info '    (WSL2, Docker Desktop et le bac à sable Windows ne marcheront plus tant qu''Hyper-V sera désactivé.)'
    } else {
        Ok 'Aucun conflit : VirtualBox aura toute la puissance du PC'
    }
}

# ----------------------------------------------------------------------------------------------
# Installation des logiciels : fichiers déjà présents d'abord, winget sinon
# ----------------------------------------------------------------------------------------------
function Installer-Fichier-Local([string]$Fichier, [string]$Nom) {
    Info ("Installation de {0} depuis le fichier déjà présent : {1}" -f $Nom, (Split-Path -Leaf $Fichier))
    if ($Fichier -like '*.msi') {
        $p = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', ('"{0}"' -f $Fichier), '/qn', '/norestart') -Wait -PassThru
    } elseif ($Nom -eq 'VirtualBox') {
        $p = Start-Process -FilePath $Fichier -ArgumentList @('--silent', '--ignore-reboot') -Wait -PassThru
    } else {
        $p = Start-Process -FilePath $Fichier -ArgumentList @('/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-') -Wait -PassThru
    }
    Ecrire-Journal ("{0} (fichier local) -> code {1}" -f $Nom, $p.ExitCode)
    return ($p.ExitCode -eq 0 -or $p.ExitCode -eq 3010 -or $p.ExitCode -eq 1641)
}

function Installer-Avec-Winget([string]$Id, [string]$Nom) {
    Info ("Téléchargement et installation de {0}... (quelques minutes)" -f $Nom)
    $sortie = & winget.exe install --id $Id --exact --silent --disable-interactivity --accept-package-agreements --accept-source-agreements 2>&1
    $code = $LASTEXITCODE
    $sortie | ForEach-Object { Ecrire-Journal ("winget: " + $_) }
    Ecrire-Journal ("winget {0} -> code {1}" -f $Id, $code)
    # 0 = installé ; -1978335189 = déjà à jour ; -1978335135 = déjà installé
    return ($code -eq 0 -or $code -eq -1978335189 -or $code -eq -1978335135)
}

function Installer-Logiciels($plan) {
    Etape 'Installation de VirtualBox, Vagrant et git (seulement ce qui manque)'
    $aInstaller = @()
    if (-not $plan.VirtualBox.Present) { $aInstaller += @{ Cle = 'VirtualBox'; Id = 'Oracle.VirtualBox'; Nom = 'VirtualBox'; Fichier = $plan.VirtualBox.Fichier } }
    if (-not $plan.Vagrant.Present) { $aInstaller += @{ Cle = 'Vagrant'; Id = 'Hashicorp.Vagrant'; Nom = 'Vagrant'; Fichier = $plan.Vagrant.Fichier } }
    if (-not $plan.Git.Present) { $aInstaller += @{ Cle = 'Git'; Id = 'Git.Git'; Nom = 'git'; Fichier = $plan.Git.Fichier } }

    if ($aInstaller.Count -eq 0) {
        Ok 'VirtualBox et Vagrant sont déjà installés : rien à télécharger'
        return $false
    }

    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    foreach ($m in $aInstaller) {
        if ($m.Fichier) {
            $reussi = Installer-Fichier-Local $m.Fichier $m.Nom
        } elseif ($winget) {
            $reussi = Installer-Avec-Winget $m.Id $m.Nom
        } else {
            Arreter-Proprement "« winget » (l'installateur de Windows) est introuvable." @(
                'Il est fourni avec Windows 11 et les Windows 10 à jour. Pour l''obtenir :',
                "  - ouvre le Microsoft Store, cherche « Programme d'installation d'applications » (App Installer) et clique sur Mettre à jour / Installer ;",
                '  - puis relance ce script.',
                '',
                'Ou télécharge à la main les fichiers listés dans hors-ligne\LISEZMOI.md, mets-les dans le dossier « hors-ligne »,',
                'puis relance ce script : il les installe tout seul.')
        }
        if (-not $reussi) {
            Montrer-Fin-Du-Journal
            Arreter-Proprement ("L'installation de {0} a échoué." -f $m.Nom) @(
                'Vérifie ta connexion internet (et que ton antivirus ne bloque pas l''installation), puis relance ce script.',
                'Si ça échoue encore, télécharge-le depuis le site officiel (liens dans hors-ligne\LISEZMOI.md), mets-le dans le dossier « hors-ligne », puis relance ce script.')
        }
        Ok ("{0} installé" -f $m.Nom)
    }

    Actualiser-Chemin
    return $true
}

function Verifier-Outils([bool]$VenaitdInstaller) {
    $vbox = Chercher-VBoxManage
    $vag = Chercher-Vagrant
    $vboxOk = $false
    $vagOk = $false
    if ($vbox) { $v = & $vbox --version 2>&1; $vboxOk = ($LASTEXITCODE -eq 0); Info ("VirtualBox : " + ($v | Select-Object -First 1)); Ecrire-Journal ("VBoxManage --version -> {0}" -f $LASTEXITCODE) }
    if ($vag) { $g = & $vag --version 2>&1; $vagOk = ($LASTEXITCODE -eq 0); Info ("Vagrant    : " + ($g | Select-Object -First 1)) }

    if ($VenaitdInstaller -and ((-not $vboxOk) -or (-not $vagOk) -or (Redemarrage-En-Attente))) {
        Arreter-Proprement 'Un redémarrage de Windows est nécessaire.' @(
            "VirtualBox et Vagrant viennent d'être installés : Windows doit redémarrer pour terminer (pilotes réseau de VirtualBox).",
            '',
            '  1. Redémarre ton ordinateur.',
            '  2. Relance ce script (clic droit > Exécuter avec PowerShell, ou double-clic sur demarrer.bat).',
            "     Il reprend exactement là où il s'est arrêté, sans rien retélécharger.") 0
    }
    if (-not $vboxOk -or -not $vagOk) {
        Arreter-Proprement 'VirtualBox ou Vagrant ne répond pas.' @(
            'Redémarre ton ordinateur puis relance ce script.',
            "Si le problème continue : désinstalle VirtualBox et Vagrant (Paramètres > Applications), puis relance ce script.")
    }
    return @{ VBox = $vbox; Vagrant = $vag }
}

# ----------------------------------------------------------------------------------------------
# Le projet : dossier courant si déjà là, sinon clonage
# ----------------------------------------------------------------------------------------------
function Preparer-Projet {
    Etape 'Récupération du projet'
    if (Test-Path -LiteralPath (Join-Path $Script:Racine 'Vagrantfile')) {
        Ok ("Projet trouvé : " + $Script:Racine)
        return $Script:Racine
    }
    $git = Chercher-Git
    if (-not $git) {
        Arreter-Proprement 'git est introuvable.' @('Relance ce script (il installe git), ou télécharge le projet en ZIP sur GitHub (bouton vert Code > Download ZIP) et lance le script depuis le dossier décompressé.')
    }
    $base = $env:USERPROFILE
    if ($base -match '[^\u0020-\u007E]') { $base = $env:SystemDrive + '\' }    # accents dans le nom d'utilisateur : Vagrant s'y perd
    $cible = Join-Path $base 'Harden-defense'
    if (Test-Path -LiteralPath (Join-Path $cible 'Vagrantfile')) {
        Info ("Projet déjà présent : " + $cible + " (mise à jour)")
        & $git -C $cible pull --ff-only 2>&1 | ForEach-Object { Ecrire-Journal ("git: " + $_) }
        return $cible
    }
    Info ("Téléchargement du projet (quelques Mo) dans " + $cible)
    & $git clone --depth 1 https://github.com/atobouh/Harden-defense.git $cible 2>&1 | ForEach-Object { Ecrire-Journal ("git: " + $_) }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $cible 'Vagrantfile'))) {
        Montrer-Fin-Du-Journal
        Arreter-Proprement 'Le téléchargement du projet a échoué.' @(
            'Vérifie ta connexion internet. Sinon, télécharge le projet en ZIP sur GitHub (bouton vert Code > Download ZIP), décompresse-le,',
            'puis lance setup-windows.ps1 depuis ce dossier.')
    }
    Ok 'Projet téléchargé'
    return $cible
}

# ----------------------------------------------------------------------------------------------
# Vagrant : sortie traduite en français + reprise automatique
# ----------------------------------------------------------------------------------------------
$Script:DernierPourcent = -1
function Traduire-Ligne([string]$Ligne) {
    $l = $Ligne -replace '\x1B\[[0-9;]*[A-Za-z]', ''
    $l = $l.TrimEnd()
    if ($l -eq '') { return }
    Ecrire-Journal ("vagrant: " + $l)

    if ($l -match "could not be found|Adding box") { Dire '    Ajout de l''image Ubuntu...' 'Gray'; return }
    if ($l -match 'Progress: (\d+)%') {
        $p = [int]$Matches[1]
        if ($p -ge $Script:DernierPourcent + 10 -or ($p -eq 100 -and $Script:DernierPourcent -ne 100)) { $Script:DernierPourcent = $p; Dire ("      téléchargement : {0} %" -f $p) 'DarkGray' }
        return
    }
    if ($l -match 'Importing base box') { Dire '    Importation de l''image dans VirtualBox...' 'Gray'; return }
    if ($l -match 'Booting VM') { Dire '    Démarrage de la machine virtuelle...' 'Gray'; return }
    if ($l -match 'Waiting for machine to boot') { Dire '    Attente du démarrage d''Ubuntu (1 à 3 minutes)...' 'Gray'; return }
    if ($l -match 'Mounting shared folders') { Dire '    Montage du dossier du projet dans la machine...' 'Gray'; return }
    if ($l -match 'Running provisioner') { Dire '    Installation du laboratoire dans la machine (10 à 15 minutes)...' 'Gray'; return }
    if ($l -match 'Machine already provisioned|already running') { Dire '    La machine est déjà installée et démarrée.' 'Gray'; return }
    if ($l -match 'déjà installé : rien à refaire') { Dire '    Laboratoire déjà installé dans la machine : rien à refaire.' 'Green'; return }
    if ($l -match '\[(\d)/7\]\s*(.+)$') { Dire ("    Laboratoire, étape {0}/7 : {1}" -f $Matches[1], $Matches[2]) 'Gray'; return }
    if ($l -match 'Installation terminée') { Dire '    Laboratoire installé.' 'Green'; return }
    if ($l -match 'error|erreur|failed|échec|ERREUR') { Dire ("    " + $l) 'Yellow'; return }
}

function Lancer-Vagrant([string]$Vagrant, [string[]]$Arguments) {
    # Retourne le code de sortie ; tout est écrit dans le journal.
    Ecrire-Journal ("> vagrant " + ($Arguments -join ' '))
    $Script:DernierPourcent = -1
    & $Vagrant @Arguments 2>&1 | ForEach-Object { Traduire-Ligne ([string]$_) }
    return $LASTEXITCODE
}

function Expliquer-Echec {
    # On lit le journal pour reconnaître les erreurs fréquentes et dire quoi faire.
    $texte = ''
    try { $texte = (Get-Content -Path $Script:Journal -Tail 120 -ErrorAction Stop) -join "`n" } catch { }
    if ($texte -match 'VERR_NEM|VERR_VMX|VT-x is not available|AMD-V|VERR_SVM|raw-mode|HostNetworkInterface|E_FAIL \(0x80004005\)') {
        return @('Cause probable : Hyper-V / WSL2 (ou « Intégrité de la mémoire ») empêche VirtualBox de démarrer la machine.',
            'Solution : relance avec la désactivation d''Hyper-V, puis redémarre le PC :',
            '    powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1 -DesactiverHyperV',
            '(Tu peux aussi désactiver « Intégrité de la mémoire » : Sécurité Windows > Sécurité de l''appareil > Isolation du noyau.)')
    }
    if ($texte -match 'VBoxNetAdp|VBoxDrv|NS_ERROR_FAILURE|kernel driver|Kernel driver|not installed') {
        return @('Cause probable : les pilotes de VirtualBox ne sont pas encore chargés.', 'Solution : redémarre Windows, puis relance ce script.')
    }
    if ($texte -match 'SSL|certificate|Could not resolve host|timed out|Timeout|The requested URL returned error|curl') {
        return @('Cause probable : problème de connexion internet, ou un antivirus / un pare-feu / un VPN qui bloque le téléchargement.',
            'Solution : vérifie ta connexion, désactive le VPN, mets l''antivirus en pause le temps de l''installation, puis relance ce script (il reprend où il en était, les fichiers déjà téléchargés sont conservés).')
    }
    if ($texte -match 'Access is denied|Accès refusé|antivirus|Quarantin') {
        return @('Cause probable : un antivirus bloque VirtualBox ou Vagrant.', "Solution : ajoute le dossier du projet et VirtualBox aux exceptions de l'antivirus (ou mets-le en pause), puis relance ce script.")
    }
    if ($texte -match 'timeout|Timed out while waiting for the machine to boot') {
        return @("La machine met trop de temps à démarrer (PC chargé ou Hyper-V actif).", 'Solution : ferme les autres programmes et relance ce script (il reprend).')
    }
    return @('Relance simplement ce script : il reprend là où il s''est arrêté (rien n''est perdu, rien n''est retéléchargé).')
}

function Attendre-Dashboard {
    Info 'Attente du dashboard (http://localhost:5000)...'
    $fin = (Get-Date).AddMinutes(6)
    while ((Get-Date) -lt $fin) {
        try {
            $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000/api/lab' -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Preparer-Image($vag, $plan) {
    # L'image Ubuntu : déjà ajoutée, ou fichier trouvé sur le PC (aucun téléchargement), ou téléchargement reprenable.
    $deja = Boite-Deja-Ajoutee $vag
    if ($deja) {
        Ok ("Image déjà présente : {0} (aucun téléchargement)" -f $deja)
        if ($deja -eq $BoiteLabo) { Set-Content -Path (Join-Path (Get-Location).Path '.hd-box') -Value $BoiteLabo -Encoding ASCII }
        return
    }
    $fichier = $null
    $nom = $BoiteUbuntu
    if ($plan -and $plan.Image.Fichier) { $fichier = $plan.Image.Fichier; $nom = $plan.Image.NomBoite }
    if ($fichier) {
        Info ("Ajout de l'image depuis le fichier trouvé sur ton PC : {0}" -f $fichier)
        $code = Lancer-Vagrant $vag @('box', 'add', '--name', $nom, $fichier)
        if ($code -ne 0) {
            Montrer-Fin-Du-Journal
            Arreter-Proprement "Ce fichier d'image n'a pas pu être ajouté." @("Le fichier est peut-être incomplet. Supprime-le ou télécharge-le à nouveau, puis relance ce script.")
        }
        if ($nom -eq $BoiteLabo) { Set-Content -Path (Join-Path (Get-Location).Path '.hd-box') -Value $BoiteLabo -Encoding ASCII }
        Ok 'Image ajoutée (aucun téléchargement)'
        return
    }
    Info ("Téléchargement de l'image Ubuntu : environ {0}, une seule fois." -f (Mo $Taille.ImageUbuntu))
    $ok = $false
    for ($i = 1; $i -le 3 -and -not $ok; $i++) {
        if ($i -gt 1) { Avertir ("Nouvelle tentative du téléchargement ({0}/3)..." -f $i); Start-Sleep -Seconds 5 }
        $ok = ((Lancer-Vagrant $vag @('box', 'add', $BoiteUbuntu, '--provider', 'virtualbox')) -eq 0)
    }
    if (-not $ok) {
        Montrer-Fin-Du-Journal
        Arreter-Proprement "Le téléchargement de l'image Ubuntu a échoué." (@(Expliquer-Echec) + @('', "Astuce : télécharge l'image sur un autre PC / avec une autre connexion (lien dans hors-ligne\LISEZMOI.md), mets-la dans le dossier « hors-ligne », puis relance ce script."))
    }
}

function Demarrer-Laboratoire($outils, [string]$Dossier, $plan) {
    Etape 'Création et démarrage de la machine virtuelle'
    Set-Location -Path $Dossier
    $vag = $outils.Vagrant

    # Vagrant s'embrouille si le profil Windows contient des accents : on met ses fichiers à un endroit simple.
    if ($env:USERPROFILE -match '[^\u0020-\u007E]' -and -not $env:VAGRANT_HOME) {
        $env:VAGRANT_HOME = Join-Path $env:SystemDrive 'vagrant-home'
        Info ("Nom d'utilisateur avec accents : fichiers Vagrant placés dans " + $env:VAGRANT_HOME)
    }

    Preparer-Image $vag $plan

    # La machine : création + installation du laboratoire. « --provision » reprend l'installation si elle avait été interrompue ;
    # elle ne refait rien si tout est déjà installé (un repère est posé dans la machine à la fin).
    $reussi = $false
    for ($i = 1; $i -le 3 -and -not $reussi; $i++) {
        if ($i -gt 1) { Avertir ("Reprise automatique ({0}/3) : rien n'est perdu, rien n'est retéléchargé..." -f $i); Start-Sleep -Seconds 8 }
        $reussi = ((Lancer-Vagrant $vag @('up', '--provision')) -eq 0)
    }
    if (-not $reussi) {
        Montrer-Fin-Du-Journal
        Arreter-Proprement "La machine virtuelle n'a pas pu être installée ou démarrée." (Expliquer-Echec)
    }
    Ok 'Machine virtuelle démarrée et laboratoire installé'
}

function Ouvrir-Dashboard {
    Etape 'Ouverture du dashboard'
    if (Attendre-Dashboard) {
        Ok 'Le dashboard répond'
        try { Start-Process 'http://localhost:5000' } catch { Info 'Ouvre ton navigateur sur http://localhost:5000' }
        Write-Host ''
        Write-Host '  Terminé !  Le dashboard est ouvert : http://localhost:5000' -ForegroundColor Green
        Write-Host '     1. Clique sur « Lancer la démonstration » : les 4 attaques partent, le tableau se remplit.' -ForegroundColor White
        Write-Host '     2. Clique sur « Protection » (en haut), attends 10 secondes, relance la démonstration : elles sont arrêtées.' -ForegroundColor White
        Write-Host ''
        Write-Host '  Les fois suivantes :  demarrer.bat (allumer)  -  arreter.bat (éteindre)  -  desinstaller.bat (tout effacer)' -ForegroundColor DarkGray
    } else {
        Montrer-Fin-Du-Journal
        Arreter-Proprement "Le dashboard ne répond pas encore." @(
            "La machine tourne mais le dashboard n'est pas prêt. Attends 2 minutes, puis ouvre http://localhost:5000.",
            "Si rien ne s'affiche : relance ce script (il répare l'installation).")
    }
}

function Trouver-Outils-Ou-Arreter {
    Actualiser-Chemin
    $vag = Chercher-Vagrant
    if (-not $vag) { Arreter-Proprement "Vagrant n'est pas installé." @('Lance d''abord l''installation : double-clique sur demarrer.bat (ou ce script sans option).') }
    return @{ Vagrant = $vag; VBox = (Chercher-VBoxManage) }
}

function Proposer-Vm-Existante($plan) {
    # Si l'étudiant a déjà une VM Ubuntu (celle du projet de départ), on lui propose l'option la plus légère.
    $vm = Trouver-Vm-Ubuntu
    if (-not $vm) { return }
    $economie = 0
    if (-not $plan.VirtualBox.Present) { $economie += $Taille.VirtualBox }
    if (-not $plan.Vagrant.Present) { $economie += $Taille.Vagrant }
    if (-not $plan.Image.Present -and -not $plan.Image.Fichier) { $economie += $Taille.ImageUbuntu }
    Write-Host ''
    Write-Host ("  Tu as déjà une machine virtuelle Ubuntu dans VirtualBox : « {0} »." -f $vm) -ForegroundColor Cyan
    Write-Host ("  Option légère : y installer le laboratoire directement. Il ne reste que les paquets Ubuntu à télécharger (environ {0}), " -f (Mo $Taille.PaquetsUbuntu)) -ForegroundColor Cyan
    if ($economie -gt 0) { Write-Host ("  soit environ {0} de moins." -f (Mo $economie)) -ForegroundColor Cyan }
    $rep = 'N'
    try { $rep = Read-Host "  Utiliser ta VM existante ? Tape O (oui, option légère) ou N (non, tout automatique)" } catch { }
    if ($rep -match '^[OoYy]') {
        Write-Host ''
        Write-Host '  Dans ta VM Ubuntu, ouvre un terminal et tape ces 3 lignes (la VM doit avoir internet) :' -ForegroundColor White
        Write-Host '      sudo apt install -y git' -ForegroundColor Yellow
        Write-Host '      git clone https://github.com/atobouh/Harden-defense.git && cd Harden-defense' -ForegroundColor Yellow
        Write-Host '      sudo ./install.sh' -ForegroundColor Yellow
        Write-Host '  Puis ouvre le navigateur DE LA VM sur http://localhost:5000 (rien à régler de plus).' -ForegroundColor White
        Write-Host '  Pas de git dans la VM ? Copie le dossier du projet dans la VM (clé USB, dossier partagé), puis : sudo ./install.sh' -ForegroundColor DarkGray
        Attendre-Fin
        exit 0
    }
}

# ----------------------------------------------------------------------------------------------
# Programme principal
# ----------------------------------------------------------------------------------------------
try {
    # Premier lancement par « demarrer.bat » : si rien n'est encore installé ou créé, on fait l'installation complète.
    if ($Action -eq 'Demarrer' -and ((-not (Chercher-Vagrant)) -or (-not (Test-Path -LiteralPath (Join-Path $Script:Racine '.vagrant'))))) { $Action = 'Installer' }
    switch ($Action) {
        'Installer' {
            $plan = @(Calculer-Plan)[-1]
            Afficher-Plan $plan
            Proposer-Vm-Existante $plan
            $pc = @(Verifier-Pc)[-1]
            Gerer-HyperV $pc
            $viensd = [bool]@(Installer-Logiciels $plan)[-1]
            $outils = Verifier-Outils $viensd
            $dossier = @(Preparer-Projet)[-1]
            Set-Location -Path $dossier
            $plan = @(Calculer-Plan)[-1]
            Demarrer-Laboratoire $outils $dossier $plan
            Ouvrir-Dashboard
        }
        'Demarrer' {
            $Script:EtapesTotal = 2
            $outils = Trouver-Outils-Ou-Arreter
            if (-not (Test-Path -LiteralPath (Join-Path $Script:Racine 'Vagrantfile'))) { Arreter-Proprement 'Lance ce script depuis le dossier du projet.' @() }
            Demarrer-Laboratoire $outils $Script:Racine $null
            Ouvrir-Dashboard
        }
        'Arreter' {
            $outils = Trouver-Outils-Ou-Arreter
            Write-Host "Arrêt de la machine virtuelle..." -ForegroundColor Cyan
            $code = Lancer-Vagrant $outils.Vagrant @('halt')
            if ($code -eq 0) { Write-Host 'Machine éteinte. Pour la rallumer : demarrer.bat' -ForegroundColor Green } else { Montrer-Fin-Du-Journal }
        }
        'Desinstaller' {
            $outils = Trouver-Outils-Ou-Arreter
            Write-Host ''
            Write-Host 'Cela supprime la machine virtuelle Harden Defense et tout ce qu''elle contient (VirtualBox, Vagrant et le projet restent installés).' -ForegroundColor Yellow
            $rep = ''
            try { $rep = Read-Host 'Tape O puis Entrée pour confirmer' } catch { }
            if ($rep -match '^[OoYy]') {
                $code = Lancer-Vagrant $outils.Vagrant @('destroy', '-f')
                if ($code -eq 0) { Write-Host 'Machine supprimée. Pour retirer aussi les logiciels : Paramètres > Applications (VirtualBox, Vagrant).' -ForegroundColor Green } else { Montrer-Fin-Du-Journal }
            } else { Write-Host 'Annulé : rien n''a été supprimé.' -ForegroundColor Gray }
        }
        'Exporter' {
            # Crée UN fichier contenant toute la machine installée : à envoyer par Dropbox / clé USB, il évite tout téléchargement sur un autre PC.
            $outils = Trouver-Outils-Ou-Arreter
            $sortie = Join-Path $Script:Racine 'harden-defense.box'
            Write-Host "Création de $sortie (la machine s'éteint, c'est normal ; compte 10 à 20 minutes et plus d'un Go)..." -ForegroundColor Cyan
            $code = Lancer-Vagrant $outils.Vagrant @('package', '--output', $sortie, '--force')
            if ($code -eq 0) { Write-Host ("Fichier créé : " + $sortie) -ForegroundColor Green; Write-Host "Envoie-le avec Dropbox ou une clé USB : sur l'autre PC, mets-le dans le dossier « hors-ligne » du projet, puis lance setup-windows.ps1." -ForegroundColor White } else { Montrer-Fin-Du-Journal }
        }
    }
} catch {
    Ecrire-Journal ("EXCEPTION : " + $_.Exception.Message)
    Ecrire-Journal ($_.ScriptStackTrace)
    Montrer-Fin-Du-Journal
    Write-Host ''
    Write-Host ("  X  Erreur inattendue : " + $_.Exception.Message) -ForegroundColor Red
    Write-Host '     Relance le script : il reprend là où il s''est arrêté. Si ça se reproduit, envoie le journal ci-dessus.' -ForegroundColor Yellow
    Attendre-Fin
    exit 1
}
Attendre-Fin
exit 0
