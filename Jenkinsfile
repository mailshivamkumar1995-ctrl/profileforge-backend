﻿// ProfileForge AI — Backend Jenkins Pipeline
// Uses the profileforge-pipeline shared library
@Library('profileforge-pipeline') _

pipeline {
    agent {
        kubernetes {
            label 'backend-build'
            yaml """
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: python
    image: python:3.12-slim
    command: [cat]
    tty: true
    resources:
      requests:
        memory: "1Gi"
        cpu: "500m"
  - name: docker
    image: docker:24-dind
    securityContext:
      privileged: true
    volumeMounts:
    - name: docker-sock
      mountPath: /var/run/docker.sock
  volumes:
  - name: docker-sock
    hostPath:
      path: /var/run/docker.sock
"""
        }
    }

    environment {
        REGISTRY          = 'ghcr.io'
        IMAGE_NAME        = "ghcr.io/${GITHUB_REPOSITORY_OWNER}/profileforge-backend"
        PYTHON_VERSION    = '3.12'
        DJANGO_SETTINGS   = 'config.settings.test'
        GITOPS_REPO       = 'profileforge-infrastructure'
        TRIVY_CONFIG      = 'security/trivy.yaml'
        GITLEAKS_CONFIG   = 'security/.gitleaks.toml'
    }

    options {
        timeout(time: 45, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds(abortPrevious: true)
        timestamps()
    }

    stages {
        // ───────────────────────────────────────────
        // CHECKOUT
        // ───────────────────────────────────────────
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.GIT_SHA_SHORT = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim()
                    env.IMAGE_TAG = "${IMAGE_NAME}:sha-${GIT_SHA_SHORT}"
                }
            }
        }

        // ───────────────────────────────────────────
        // PARALLEL: LINT + TYPE CHECK + SECRET SCAN
        // ───────────────────────────────────────────
        stage('Code Quality') {
            parallel {
                stage('Lint') {
                    steps {
                        container('python') {
                            sh '''
                                pip install ruff isort -q
                                ruff check .
                                ruff format --check .
                                isort --check-only .
                            '''
                        }
                    }
                }

                stage('Type Check') {
                    steps {
                        container('python') {
                            sh '''
                                pip install -r requirements/dev.txt -q
                                mypy . --config-file pyproject.toml
                            '''
                        }
                    }
                }

                stage('Secret Scan') {
                    steps {
                        container('python') {
                            sh '''
                                pip install gitleaks -q 2>/dev/null || \
                                  wget -q https://github.com/gitleaks/gitleaks/releases/download/v8.18.0/gitleaks_8.18.0_linux_x64.tar.gz \
                                  -O - | tar xz -C /usr/local/bin/
                                gitleaks detect --source . \
                                  --config ${GITLEAKS_CONFIG} \
                                  --no-git \
                                  --exit-code 1
                            '''
                        }
                    }
                }
            }
        }

        // ───────────────────────────────────────────
        // PARALLEL: UNIT + SECURITY TESTS
        // ───────────────────────────────────────────
        stage('Tests') {
            parallel {
                stage('Unit Tests') {
                    steps {
                        container('python') {
                            sh '''
                                pip install -r requirements/dev.txt -q
                                pytest -m "not integration and not e2e and not slow" \
                                  --cov=apps --cov=core --cov=celery_app \
                                  --cov-report=xml:coverage-unit.xml \
                                  --cov-report=term-missing \
                                  -q
                            '''
                        }
                    }
                    post {
                        always {
                            junit 'test-results-unit.xml'
                            publishCoverage adapters: [coberturaAdapter('coverage-unit.xml')]
                        }
                    }
                }

                stage('Security Tests') {
                    steps {
                        container('python') {
                            sh '''
                                pip install -r requirements/dev.txt -q
                                pytest apps/security_tests/ -v \
                                  --cov=apps/security_tests \
                                  --cov-report=xml:coverage-security.xml \
                                  -q
                            '''
                        }
                    }
                }
            }
        }

        // ───────────────────────────────────────────
        // QUALITY GATE
        // ───────────────────────────────────────────
        stage('Quality Gate') {
            steps {
                container('python') {
                    sh '''
                        pip install coverage -q
                        python3 -c "
import xml.etree.ElementTree as ET, sys, glob
rates = []
for f in glob.glob('coverage-*.xml'):
    root = ET.parse(f).getroot()
    rate = float(root.attrib.get('line-rate', 0)) * 100
    rates.append((f, rate))
    print(f'{f}: {rate:.1f}%')
if rates:
    avg = sum(r for _, r in rates) / len(rates)
    print(f'Average: {avg:.1f}%  Threshold: 85%')
    if avg < 85:
        print('FAIL: Coverage below 85%')
        sys.exit(1)
print('PASS: Quality gate met')
"
                    '''
                }
            }
        }

        // ───────────────────────────────────────────
        // DEPENDENCY AUDIT
        // ───────────────────────────────────────────
        stage('Dependency Audit') {
            steps {
                container('python') {
                    sh '''
                        pip install pip-audit -q
                        pip-audit -r requirements/base.txt --severity high
                    '''
                }
            }
        }

        // ───────────────────────────────────────────
        // DOCKER BUILD + SCAN
        // ───────────────────────────────────────────
        stage('Docker Build') {
            when {
                anyOf {
                    branch 'main'
                    branch 'develop'
                    tag 'v*'
                }
            }
            steps {
                container('docker') {
                    script {
                        dockerBuild(
                            imageName: env.IMAGE_NAME,
                            imageTag: env.GIT_SHA_SHORT,
                            context: '.',
                            target: 'production',
                            trivyConfig: env.TRIVY_CONFIG
                        )
                    }
                }
            }
        }

        // ───────────────────────────────────────────
        // PUSH IMAGE (main + tags only)
        // ───────────────────────────────────────────
        stage('Push Image') {
            when {
                anyOf {
                    branch 'main'
                    tag 'v*'
                }
            }
            steps {
                container('docker') {
                    withCredentials([usernamePassword(
                        credentialsId: 'ghcr-credentials',
                        usernameVariable: 'REGISTRY_USER',
                        passwordVariable: 'REGISTRY_PASS'
                    )]) {
                        sh '''
                            echo "$REGISTRY_PASS" | docker login ${REGISTRY} -u "$REGISTRY_USER" --password-stdin
                            docker push ${IMAGE_TAG}
                            docker tag ${IMAGE_TAG} ${IMAGE_NAME}:latest
                            docker push ${IMAGE_NAME}:latest
                        '''
                    }
                }
            }
        }

        // ───────────────────────────────────────────
        // DEPLOY TO DEV (main branch only)
        // ───────────────────────────────────────────
        stage('Deploy to Dev') {
            when {
                branch 'main'
            }
            steps {
                script {
                    deployGitOps(
                        app: 'backend',
                        environment: 'dev',
                        imageTag: "sha-${env.GIT_SHA_SHORT}",
                        gitopsRepo: env.GITOPS_REPO
                    )
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline succeeded: ${env.IMAGE_TAG}"
        }
        failure {
            echo "Pipeline failed on branch ${env.BRANCH_NAME}"
        }
        always {
            cleanWs()
        }
    }
}
