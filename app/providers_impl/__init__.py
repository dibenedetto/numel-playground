# providers_impl — Concrete provider implementations.
#
# Local implementations (no external dependencies) for development:
#   - LocalAuthProvider      — JSON-file user store + JWT
#   - LocalFSDataProvider    — Plain filesystem with JSON metadata
#   - LocalProcessExecProvider — In-process execution (current Numel behavior)
#
# Production implementations (require external services):
#   - DjangoAuthProvider     — Django REST auth service
#   - GiteaDataProvider      — Gitea REST API
#   - DockerExecProvider     — Docker container per execution
