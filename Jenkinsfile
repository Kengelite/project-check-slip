pipeline {
    agent any

    environment {
        BUILD_TAG = "${env.BUILD_NUMBER}"
    }

    parameters {
        booleanParam(
            name: 'CLEAN_VOLUMES',
            defaultValue: false,
            description: 'เลือก True หากต้องการลบข้อมูล Database ทิ้งแล้วเริ่มใหม่ (ระวัง! ข้อมูลสลิปหายทั้งหมด)'
        )
        string(
            name: 'SERVER_IP',
            defaultValue: '10.198.110.26',
            description: 'IP ของ Server (ใช้สำหรับแสดงผลลิงก์ตอน Deploy สำเร็จ)'
        )
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    checkout scm
                    env.GIT_COMMIT_SHORT = sh(returnStdout: true, script: 'git rev-parse --short HEAD').trim()
                    echo "Build: ${BUILD_TAG}, Commit: ${env.GIT_COMMIT_SHORT}"
                }
            }
        }

        stage('Prepare Environment') {
            steps {
                script {
                    echo "Creating .env file from Jenkins Credentials..."
                    //  อย่าลืมไปสร้าง Credentials เหล่านี้ในระบบ Jenkins ด้วยนะครับ
                    withCredentials([
                        string(credentialsId: 'POSTGRES_PASSWORD', variable: 'DB_PASS'),
                        string(credentialsId: 'FASTAPI_SECRET_KEY', variable: 'SECRET_KEY'),
                        string(credentialsId: 'GOOGLE_CLIENT_ID', variable: 'GOOGLE_ID'),
                        string(credentialsId: 'GOOGLE_CLIENT_SECRET', variable: 'GOOGLE_SECRET')
                    ]) {
                        writeFile file: '.env', text: """
POSTGRES_USER=admin
POSTGRES_PASSWORD=${env.DB_PASS}
POSTGRES_DB=slip_db

SECRET_KEY=${env.SECRET_KEY}
GOOGLE_CLIENT_ID=${env.GOOGLE_ID}
GOOGLE_CLIENT_SECRET=${env.GOOGLE_SECRET}
""".stripIndent()
                    }
                }
            }
        }

        stage('Deploy Stack') {
            steps {
                script {
                    def downCmd = 'docker compose down'
                    if (params.CLEAN_VOLUMES) {
                        downCmd = 'docker compose down -v'
                        echo "Cleaning volumes and stopping containers..."
                    }
                    sh downCmd
                    
                    echo "Building and starting containers..."
                    sh 'docker compose up -d --build'
                }
            }
        }

        stage('Health Check') {
            steps {
                script {
                    echo "Waiting for services to be ready (15s)..."
                    sleep 15
                    
                    echo "Current Container Status:"
                    sh 'docker compose ps'
                    
                    echo "Testing Nginx/FastAPI connection..."
                    // ยิงเช็คไปที่ localhost พอร์ต 80 (Nginx) ว่าเว็บอัปขึ้นมาหรือยัง
                    sh "curl -f http://localhost/ || (echo 'Web/API not responding' && exit 1)"
                    
                    echo " All systems GO!"
                }
            }
        }
    }

    post {
        always {
            echo "Cleaning up dangling images..."
            sh 'docker image prune -f'
        }
        success {
            echo "--------------------------------------------------------"
            echo "🚀 Deploy สำเร็จแล้ว!"
            echo "🌐 Website / API : http://${params.SERVER_IP}"
            echo "🗄️ pgAdmin Database: http://${params.SERVER_IP}:5050"
            echo "--------------------------------------------------------"
        }
        failure {
            echo "❌ Deploy ล้มเหลว! กำลังดึง Logs 50 บรรทัดสุดท้ายมาให้ดู..."
            sh 'docker compose logs --tail=50'
        }
    }
}