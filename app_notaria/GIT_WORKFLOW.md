# Guía de Versionamiento y Commits
## App Notaria

---

## Configuración inicial de Git (primera vez)

### 1. Instalar Git
- **Windows**: Descarga desde https://git-scm.com/download/win
- **Mac**: `brew install git`
- **Linux**: `sudo apt-get install git`

### 2. Configurar tu identidad

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "tu@email.com"
```

### 3. Inicializar el repositorio

```bash
cd c:\Users\EQUIPO 25\Desktop\Beneficencia\app_notaria
git init
git add .
git commit -m "Initial commit: App Notaria v1.0.0"
```

---

## Primer Commit

### Contenido del primer commit

```
Initial commit: App Notaria v1.0.0

Incluye:
- Aplicación FastAPI completa
- Interfaz web con dashboard
- Scripts de importación de datos
- Generación de certificados y recibos
- Sistema de logs integrado
- Scripts de despliegue a producción
- Documentación completa
```

### Comando para el primer commit

```bash
git add .
git commit -m "Initial commit: App Notaria v1.0.0

- Complete FastAPI backend with Supabase integration
- Web UI with statistics dashboard
- Certificate generation and email sending
- Data import scripts from Excel
- Deployment scripts for Windows/Linux/Mac
- Complete documentation and changelog"
```

---

## Workflow de desarrollo recomendado

### 1. Crear rama para nueva feature

```bash
git checkout -b feature/nombre-feature
```

### 2. Hacer cambios y commits

```bash
# Hacer cambios...
git add .
git commit -m "Add feature: descripción breve"
```

### 3. Subir rama

```bash
git push origin feature/nombre-feature
```

### 4. Merge a main

```bash
git checkout main
git merge feature/nombre-feature
```

---

## Convención de commits

Usa este formato para mensajes de commit:

```
<tipo>(<scope>): <subject>

<body>

<footer>
```

### Tipos válidos
- **feat**: Nueva característica
- **fix**: Corrección de bug
- **docs**: Cambios en documentación
- **style**: Cambios de formato (sin lógica)
- **refactor**: Refactorización de código
- **perf**: Mejora de performance
- **test**: Agregar o actualizar tests
- **chore**: Cambios en build, deps, etc

### Ejemplos

```bash
# Nueva característica
git commit -m "feat(api): add new endpoint for statistics"

# Bug fix
git commit -m "fix(auth): handle token expiration correctly"

# Documentación
git commit -m "docs(deployment): add troubleshooting section"

# Refactoring
git commit -m "refactor(db): simplify query logic"
```

---

## Tagging de versiones

### Crear tag para versión

```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

### Ver tags

```bash
git tag -l
git show v1.0.0
```

---

## Ramas principales

- **main**: Código en producción
- **develop**: Rama de desarrollo
- **feature/***: Nuevas características
- **bugfix/***: Correcciones de bugs
- **release/***: Preparación de release

---

## Integración continua (recomendado)

Para automatizar despliegues, puedes usar:

1. **GitHub Actions** (si usas GitHub)
2. **GitLab CI** (si usas GitLab)
3. **Jenkins** (para servidores propios)

---

## Backup y recuperación

### Crear backup del repositorio

```bash
# Local
git clone --bare . ../app_notaria.git

# O comprimir
tar -czf app_notaria_backup.tar.gz .git
```

### Restaurar desde backup

```bash
git clone ../app_notaria.git .
```

---

## Comandos útiles

```bash
# Ver estado
git status

# Ver diferencias
git diff

# Ver historial
git log --oneline -10

# Ver rama actual
git branch

# Deshacer cambios locales
git checkout -- archivo.py

# Resetear commit
git reset HEAD~1

# Ver cambios pendientes
git diff --cached
```

---

## Flujo completo para despliegue

```bash
# 1. Cambios locales
git add .
git commit -m "fix: algo importante"

# 2. Actualizar desde remoto
git pull origin main

# 3. Resolver conflictos (si hay)
# ... editar archivos ...
git add .
git commit -m "merge: resolver conflictos"

# 4. Subir cambios
git push origin main

# 5. En servidor de producción
git pull origin main
./deploy.ps1 restart  # o el script correspondiente
```

---

## Scripts auxiliares

### deploy-with-git.ps1 (Windows)
```powershell
param([string]$message = "Auto-deploy")

# Agregar cambios
git add .
git commit -m $message

# Subir a repositorio
git push origin main

# Desplegar
./deploy.ps1 restart
```

Uso:
```powershell
.\deploy-with-git.ps1 "Add new feature: XYZ"
```

### deploy-with-git.sh (Linux/Mac)
```bash
#!/bin/bash

MESSAGE="${1:-Auto-deploy}"

git add .
git commit -m "$MESSAGE"
git push origin main
./deploy.sh restart
```

Uso:
```bash
./deploy-with-git.sh "Add new feature: XYZ"
```

---

## Recursos útiles

- [Pro Git Book](https://git-scm.com/book/es/v2)
- [Git Cheat Sheet](https://github.github.com/training-kit/downloads/github-git-cheat-sheet.pdf)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Documentation](https://docs.github.com)

---

**Versión:** 1.0  
**Última actualización:** 2026-05-22
