import sqlite3
import re
import json
import os
from datetime import datetime
from db_operation import create_chroma_db, answer_without_chroma_db, answer_user_query
from visualization import create_heatmap, create_comparison_heatmap
from sohu_api import SohuGlobalAPI
from my_qianfan_llm import llm
from quart import Blueprint, request, jsonify, render_template, current_app
import logging
from content_manager import content_manager
from user_feedback import user_feedback
from personality_score import PersonalityScoreCalculator
from typing import List, Dict

# 配置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 创建蓝图
api = Blueprint('api', __name__)

# [1] rag准备

# 检查是否存在rag向量数据库
create_chroma_db("rag_shqp", "shqp_rag .txt")

# 初始化搜狐API
sohu_api = SohuGlobalAPI("https://api.sohuglobal.com")
try:
    print("Attempting to login to Sohu API...")
    if not sohu_api.login(phone="admin", password="U9xbHDJUH1pmx9hk7nXbQQ=="):
        print("Failed to login to Sohu API")
        raise Exception("Failed to login to Sohu API")
except Exception as e:
    print(f"Error during Sohu API initialization: {str(e)}")
    raise e

def extract_scores_from_text(text):
    """Extract scores from the text using regex"""
    scores = {}
    # Match patterns like "xxx = xx" or "xxx=xx"
    pattern = r'(\w+)\s*=\s*(\d+)'
    matches = re.finditer(pattern, text)
    for match in matches:
        key = match.group(1)
        value = int(match.group(2))
        scores[key] = value
    return scores

def query_personality_score(user_id):
    """Query user personality scores from database"""
    try:
        conn = sqlite3.connect("user.db")
        c = conn.cursor()
        cursor = c.execute("SELECT * from personality where id = ?", (user_id,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        conn.close()

        if row is None:
            print(f"Warning: No personality data found for user ID {user_id}")
            return None

        return row
    except Exception as e:
        print(f"Error querying personality score: {str(e)}")
        return None

def query_columns():
    """Query column names from database"""
    try:
        conn = sqlite3.connect("user.db")
        c = conn.cursor()
        cursor = c.execute("SELECT * from personality")
        columns = [description[0] for description in cursor.description]
        conn.close()
        print(f"Database columns: {columns}")  # 添加日志
        return columns
    except Exception as e:
        print(f"Error querying columns: {str(e)}")
        return []

def query_user_data(user_id):
    """查询用户的行为数据

    Args:
        user_id: 用户ID

    Returns:
        list: 用户行为数据列表
    """
    try:
        conn = sqlite3.connect("user.db")
        c = conn.cursor()
        cursor = c.execute("SELECT * FROM user_behavior WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"Error querying user data: {str(e)}")
        return []

def analyze_user_behavior(user_data, initial_scores):
    """分析用户行为并更新性格分数

    Args:
        user_data: 用户行为数据
        initial_scores: 初始性格分数

    Returns:
        list: 更新后的性格分数
    """
    try:
        # 这里可以添加更复杂的行为分析逻辑
        # 目前简单返回初始分数
        return initial_scores
    except Exception as e:
        print(f"Error analyzing user behavior: {str(e)}")
        return initial_scores

# 模拟商品数据
MOCK_PRODUCTS = [
    {
        "id": 1,
        "name": "智能手表",
        "description": "多功能智能手表，支持心率监测、运动追踪等功能",
        "category_id": 3,
        "category_name": "电子产品",
        "price": 999.00,
        "image_url": "https://via.placeholder.com/300x200?text=智能手表"
    },
    {
        "id": 2,
        "name": "运动水壶",
        "description": "大容量运动水壶，保温保冷，适合户外运动",
        "category_id": 1,
        "category_name": "饮品",
        "price": 89.00,
        "image_url": "https://via.placeholder.com/300x200?text=运动水壶"
    },
    {
        "id": 3,
        "name": "有机坚果礼盒",
        "description": "精选优质坚果，营养丰富，适合作为健康零食",
        "category_id": 2,
        "category_name": "食品",
        "price": 199.00,
        "image_url": "https://via.placeholder.com/300x200?text=有机坚果"
    },
    {
        "id": 4,
        "name": "休闲运动套装",
        "description": "舒适透气的运动套装，适合日常穿着和运动",
        "category_id": 4,
        "category_name": "服装",
        "price": 299.00,
        "image_url": "https://via.placeholder.com/300x200?text=运动套装"
    },
    {
        "id": 5,
        "name": "智能台灯",
        "description": "可调节亮度和色温的智能台灯，护眼设计",
        "category_id": 5,
        "category_name": "家居",
        "price": 199.00,
        "image_url": "https://via.placeholder.com/300x200?text=智能台灯"
    }
]

def generate_recommendations(user_id, personality_data):
    """生成个性化推荐"""
    try:
        # 使用 ContentManager 获取推荐
        recommendations = content_manager.get_recommendations(personality_data, limit=5)
        
        if not recommendations:
            logger.warning("No recommendations found")
            return []
            
        return recommendations
            
    except Exception as e:
        logger.error(f"Error generating recommendations: {str(e)}")
        return []

def get_user_operations(user_id):
    """从JSON文件中获取指定用户的操作日志

    Args:
        user_id: 用户ID

    Returns:
        dict: 用户操作日志
    """
    try:
        # 读取JSON文件
        with open('user_operations.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 过滤出指定用户的操作，并只保留重要字段
        user_operations = []
        for op in data['operations']:
            if op['user_id'] == str(user_id):
                # 只保留最关键的字段，并简化格式
                simplified_op = {
                    'a': op['action'],  # 使用简短的键名
                    't': op['time'],    # 使用简短的键名
                    'b': op['detail']['business_type'],  # 使用简短的键名
                    'c': op['detail'].get('category', '')  # 使用简短的键名
                }
                user_operations.append(simplified_op)

        # 如果没有找到用户操作，返回空列表
        if not user_operations:
            return {"ops": []}  # 使用更短的键名

        # 返回用户操作日志
        return {"ops": user_operations}  # 使用更短的键名

    except Exception as e:
        print(f"Error reading user operations: {str(e)}")
        # 如果出错，返回空操作日志
        return {"ops": []}  # 使用更短的键名

async def process_user_analysis(user_id):
    """Process user analysis and return results"""
    try:
        logger.debug(f"Starting analysis for user {user_id}")
        
        profile = query_personality_score(user_id)
        logger.debug(f"Retrieved profile: {profile}")

        if profile is None:
            logger.error(f"No profile found for user {user_id}")
            return {
                'success': False,
                'error': f'未找到用户ID {user_id} 的性格数据，请确保该用户已存在于数据库中。'
            }

        # Create initial personality scores dictionary
        initial_scores = {}
        columns = query_columns()
        logger.debug(f"Using columns: {columns}")

        for col, val in zip(columns, profile):
            if col != 'id':  # Skip the id column
                initial_scores[col] = val
        logger.debug(f"Initial scores: {initial_scores}")

        # 获取用户特定的操作日志
        user_operations = get_user_operations(user_id)
        logger.debug(f"Retrieved user operations: {user_operations}")
        
        # 限制操作日志的长度
        max_operations = 50  # 减少处理的操作记录数量
        if len(user_operations['ops']) > max_operations:
            user_operations['ops'] = user_operations['ops'][:max_operations]
            logger.warning(f"操作日志超过{max_operations}条，只处理前{max_operations}条")
        
        # 使用行为分析器分析用户行为
        behavior_analyzer = BehaviorAnalyzer()
        logger.debug("Starting behavior analysis")
        behavior_summary = await behavior_analyzer.analyze_user_behavior(user_id, user_operations['ops'])
        logger.debug(f"Behavior analysis completed. Summary: {behavior_summary}")
        
        # 使用性格分数计算器计算新分数
        calculator = PersonalityScoreCalculator()
        new_scores = calculator.update_personality_scores(behavior_summary, initial_scores)
        logger.debug(f"Updated scores: {new_scores}")
        
        # 将新分数写回数据库
        try:
            conn = sqlite3.connect("user.db")
            cursor = conn.cursor()
            
            # 构建更新语句
            update_cols = []
            update_vals = []
            for col, val in new_scores.items():
                if col != 'id':  # 跳过id列
                    update_cols.append(f"{col} = ?")
                    update_vals.append(val)
            
            if update_cols:
                update_query = f"UPDATE personality SET {', '.join(update_cols)} WHERE id = ?"
                update_vals.append(user_id)
                cursor.execute(update_query, update_vals)
                conn.commit()
                logger.info(f"Successfully updated personality scores for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating personality scores in database: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
        
        # 生成更新原因
        update_reasons = {}
        for trait in new_scores:
            if trait in initial_scores:
                old_score = float(initial_scores.get(trait, 0) or 0)
                new_score = float(new_scores.get(trait, 0) or 0)
                score_change = new_score - old_score
                
                if abs(score_change) > 0.1:  # 只记录有显著变化的特征
                    reasons = calculator.get_score_change_reasons(behavior_summary, trait)
                    update_reasons[trait] = {
                        'old_score': old_score,
                        'new_score': new_score,
                        'change': score_change,
                        'reasons': reasons or ['基于用户最近的行为模式']
                    }
        logger.debug(f"Update reasons: {update_reasons}")

        # 构建用户画像字符串
        user_profile = f"用户ID：{user_id}\n\n"
        
        # 添加行为分析
        if behavior_summary.get('behavior_categories'):
            user_profile += "行为分析：\n"
            for category, details in behavior_summary['behavior_categories'].items():
                user_profile += f"- {category}：{details['behavior_type']} ({details['count']}次)\n"
        
        # 添加特征分析
        if behavior_summary.get('trait_analysis'):
            user_profile += "\n性格特征分析：\n"
            for trait, analysis in behavior_summary['trait_analysis'].items():
                user_profile += f"- {trait}：\n"
                user_profile += f"  相关行为：{', '.join(analysis['related_behaviors'])}\n"
                user_profile += f"  行为强度：{analysis['behavior_strength']}\n"
                user_profile += f"  影响程度：{analysis['impact_level']}\n"
        
        # 添加分数变化
        if update_reasons:
            user_profile += "\n性格特征变化：\n"
            for trait, details in update_reasons.items():
                user_profile += f"- {trait}：{details['old_score']:.1f} -> {details['new_score']:.1f} "
                user_profile += f"(变化：{details['change']:+.1f})\n"
                if details['reasons']:
                    user_profile += f"  原因：{', '.join(details['reasons'])}\n"
        
        logger.debug(f"User profile string: {user_profile}")

        # 生成新的画像
        prompt = """
        请根据以下用户信息生成详细的用户画像分析：

        {user_profile}

        请从以下几个方面进行分析：

        1. 行为模式总结：
        - 分析用户的主要行为类型和频率
        - 总结用户的内容偏好和使用习惯
        - 识别用户的典型行为特征

        2. 性格特征解读：
        - 分析性格特征的变化原因
        - 解释行为与性格特征的关联
        - 评估性格特征变化的合理性

        3. 用户画像更新：
        - 基于最新数据更新用户画像
        - 突出关键的性格特征变化
        - 预测用户未来的行为趋势

        请生成一个全面且具体的分析报告。
        """

        # 格式化prompt
        logger.debug("Formatting prompt")
        formatted_prompt = prompt.format(user_profile=user_profile)
        logger.debug(f"Formatted prompt: {formatted_prompt}")

        # 使用RAG进行分析
        logger.debug("Starting RAG analysis")
        result_profile = ''.join(answer_user_query("rag_shqp", formatted_prompt))
        logger.debug(f"RAG analysis completed. Result: {result_profile}")

        # 生成热力图
        logger.debug("Generating heatmaps")
        create_heatmap(initial_scores, f"Initial Personality Heatmap for User {user_id}",
                    f"initial_heatmap_{user_id}.png")
        create_heatmap(new_scores, f"Updated Personality Heatmap for User {user_id}",
                    f"updated_heatmap_{user_id}.png")
        create_comparison_heatmap(initial_scores, new_scores,
                                f"Personality Scores Comparison for User {user_id}",
                                f"comparison_heatmap_{user_id}.png")

        # 获取推荐内容
        logger.debug("Getting recommendations")
        recommended_items = content_manager.get_recommendations(new_scores)
        logger.debug(f"Recommendations: {recommended_items}")

        # 构建返回结果
        result = {
            'success': True,
            'summary': behavior_summary,
            'profile': result_profile,
            'recommendations': recommended_items,
            'images': {
                'initial': f"initial_heatmap_{user_id}.png",
                'updated': f"updated_heatmap_{user_id}.png",
                'comparison': f"comparison_heatmap_{user_id}.png"
            }
        }
        
        logger.debug(f"Returning result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in process_user_analysis: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }

@api.route('/')
async def index():
    """显示主页"""
    logger.debug("Accessing index page")
    return await render_template('index.html')

@api.route('/users')
async def users():
    """显示用户管理页面"""
    logger.debug("Accessing user management page")
    return await render_template('users.html')

@api.route('/analyze', methods=['POST'])
async def analyze():
    """处理用户分析请求"""
    try:
        data = await request.get_json()
        user_id = data.get('user_id')
        logger.info(f"Received analysis request for user_id: {user_id}")

        if not user_id:
            logger.warning("No user_id provided in request")
            return jsonify({
                'success': False,
                'error': 'No user_id provided'
            })

        result = await process_user_analysis(user_id)
        logger.info(f"Analysis completed for user_id: {user_id}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error processing analysis: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@api.route('/feedback', methods=['POST'])
async def handle_feedback():
    """处理用户交互反馈"""
    try:
        data = await request.get_json()
        if not data:
            logger.error("No JSON data received")
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
            
        logger.debug(f"Received feedback data: {data}")
        
        user_id = data.get('user_id')
        content_id = data.get('item_id')
        interaction_type = data.get('interaction_type')
        content_type = data.get('content_type')
        
        logger.debug(f"Extracted data - user_id: {user_id}, content_id: {content_id}, "
                    f"interaction_type: {interaction_type}, content_type: {content_type}")
        
        if not all([user_id, content_id, interaction_type, content_type]):
            missing_fields = [field for field, value in {
                'user_id': user_id,
                'item_id': content_id,
                'interaction_type': interaction_type,
                'content_type': content_type
            }.items() if not value]
            
            error_msg = f"Missing required parameters: {', '.join(missing_fields)}"
            logger.warning(error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
        success = user_feedback.record_interaction(
            user_id=user_id,
            content_id=content_id,
            interaction_type=interaction_type,
            content_type=content_type
        )
        
        if success:
            response_data = {
                'success': True,
                'message': 'Interaction recorded successfully'
            }
            logger.info(f"Successfully recorded interaction for user {user_id}")
            return jsonify(response_data)
        else:
            error_msg = f"Failed to record interaction for user {user_id}"
            logger.error(error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
            
    except Exception as e:
        error_msg = f"Error handling feedback: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500

@api.route('/data_update')
async def data_update():
    """显示数据更新页面"""
    return await render_template('data_update.html')

@api.route('/update_user_data', methods=['POST'])
async def update_user_data():
    """更新用户数据"""
    try:
        logger.debug("Starting user data update")
        
        # 更新性格分数
        if user_feedback.update_personality_scores():
            # 获取分数变化
            changes = user_feedback.get_score_changes()
            logger.info(f"User data updated successfully. Changes: {changes}")
            
            return jsonify({
                'success': True,
                'changes': changes,
                'message': 'User data updated successfully'
            })
        else:
            error_msg = "Failed to update user data"
            logger.error(error_msg)
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
            
    except Exception as e:
        logger.error(f"Error updating user data: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api.route('/user_behavior/<user_id>', methods=['GET'])
async def get_user_behavior(user_id):
    """获取用户行为历史"""
    try:
        history = user_feedback.get_user_behavior_history(user_id)
        return jsonify({
            'success': True,
            'history': history
        })
    except Exception as e:
        logger.error(f"Error getting user behavior: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@api.post("/update_profile")
async def update_profile(user_id: int):
    try:
        # 获取用户操作数据
        operations = await get_user_operations(user_id)
        if not operations:
            return {"error": "未找到用户操作数据"}
        
        # 获取当前性格特征分数
        current_scores = await get_current_personality_scores(user_id)
        
        # 创建性格分数计算器
        calculator = PersonalityScoreCalculator()
        
        # 计算新的性格特征分数
        updated_scores = calculator.update_personality_scores(operations, current_scores)
        
        # 生成更新原因
        update_reasons = {}
        for trait in updated_scores:
            reasons = calculator.get_score_change_reasons(operations, trait)
            if reasons:
                update_reasons[trait] = reasons
        
        # 更新数据库
        await update_personality_scores_in_db(user_id, updated_scores)
        
        # 构建提示词
        prompt = build_profile_update_prompt(operations, current_scores, updated_scores, update_reasons)
        
        # 调用模型生成新的画像
        new_profile = await generate_new_profile(prompt)
        
        return {
            "success": True,
            "new_profile": new_profile,
            "score_changes": {
                trait: {
                    "old_score": current_scores[trait],
                    "new_score": updated_scores[trait],
                    "reasons": update_reasons.get(trait, [])
                } for trait in updated_scores
            }
        }
        
    except Exception as e:
        logger.error(f"更新用户画像时出错: {str(e)}")
        return {"error": str(e)}

def build_profile_update_prompt(operations: List[Dict], 
                              current_scores: Dict[str, float],
                              updated_scores: Dict[str, float],
                              update_reasons: Dict[str, List[str]]) -> str:
    """构建更新画像的提示词"""
    prompt = f"""基于用户最近的行为数据，更新用户画像。以下是详细分析：

[用户行为分析]
{format_operations(operations)}

[性格特征更新]
"""
    
    for trait, new_score in updated_scores.items():
        old_score = current_scores[trait]
        reasons = update_reasons.get(trait, [])
        
        prompt += f"""
- {trait}：
  旧分数：{old_score:.1f} -> 新分数：{new_score:.1f}
  变化原因：
"""
        for reason in reasons:
            prompt += f"  - {reason}\n"
    
    prompt += """
请根据以上分析，生成更新后的用户画像，重点关注：
1. 性格特征的变化及其原因
2. 用户行为模式的新发现
3. 对用户未来行为的预测
"""
    
    return prompt
