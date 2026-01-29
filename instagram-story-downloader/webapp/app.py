from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import instaloader
import os
import tempfile
import shutil
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# 환경 변수로 Instagram 계정 정보 설정
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', 'your_dummy_account')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD', 'your_password')

# Instaloader 인스턴스 생성
L = instaloader.Instaloader(
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    post_metadata_txt_pattern='',
    max_connection_attempts=3
)

# 로그인 상태 관리
logged_in = False

def login_instagram():
    """Instagram에 로그인"""
    global logged_in
    if not logged_in:
        try:
            L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            logged_in = True
            print(f"✅ Instagram 로그인 성공: {INSTAGRAM_USERNAME}")
        except Exception as e:
            print(f"❌ Instagram 로그인 실패: {str(e)}")
            raise Exception(f"Instagram 로그인 실패. 계정 정보를 확인해주세요: {str(e)}")

@app.route('/')
def index():
    """메인 페이지 제공"""
    return send_from_directory('static', 'index.html')

@app.route('/api/stories/<username>', methods=['GET'])
def get_stories(username):
    """특정 사용자의 스토리 가져오기"""
    try:
        # Instagram 로그인 (최초 1회)
        login_instagram()
        
        # 사용자 프로필 가져오기
        profile = instaloader.Profile.from_username(L.context, username)
        
        # 스토리 확인
        if not profile.has_viewable_story:
            return jsonify({
                'success': False,
                'message': f'{username} 님은 현재 스토리가 없습니다.'
            }), 404
        
        # 스토리 다운로드를 위한 임시 디렉토리
        temp_dir = tempfile.mkdtemp()
        
        stories = []
        try:
            # 스토리 가져오기
            for story in L.get_stories(userids=[profile.userid]):
                for item in story.get_items():
                    story_data = {
                        'id': item.mediaid,
                        'date': item.date_utc.strftime('%Y-%m-%d %H:%M:%S'),
                        'type': 'video' if item.is_video else 'image',
                        'url': item.video_url if item.is_video else item.url,
                        'thumbnail': item.url if item.is_video else None
                    }
                    stories.append(story_data)
            
            if not stories:
                return jsonify({
                    'success': False,
                    'message': f'{username} 님의 스토리를 가져올 수 없습니다.'
                }), 404
            
            return jsonify({
                'success': True,
                'username': username,
                'profile_pic': profile.profile_pic_url,
                'full_name': profile.full_name,
                'stories': stories
            })
            
        finally:
            # 임시 디렉토리 정리
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    except instaloader.exceptions.ProfileNotExistsException:
        return jsonify({
            'success': False,
            'message': f'{username} 사용자를 찾을 수 없습니다.'
        }), 404
    
    except instaloader.exceptions.LoginRequiredException:
        return jsonify({
            'success': False,
            'message': 'Instagram 로그인이 필요합니다. 서버 관리자에게 문의하세요.'
        }), 401
    
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'오류 발생: {str(e)}'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """서버 상태 확인"""
    return jsonify({
        'status': 'ok',
        'logged_in': logged_in,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

if __name__ == '__main__':
    # 정적 파일 디렉토리 생성
    os.makedirs('static', exist_ok=True)
    
    # 개발 서버 실행
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
