"""
Auth Decorators for Route Protection
-------------------------------------
Provides decorators for JWT authentication and role-based access control.
"""

from functools import wraps
from flask import request, jsonify, g
import jwt
import os
from dotenv import load_dotenv

load_dotenv()

def require_auth(f):
    """
    Decorator that validates JWT token and extracts user information.
    
    Extracts from Authorization header: Bearer <token>
    Sets in Flask g object:
        - g.user_id: User's UUID from token
        - g.user_email: User's email
        - g.user_role: User's role (default: 'user')
    
    Returns 401 if token is missing or invalid.
    
    Usage:
        @app.route('/protected')
        @require_auth
        def protected_route():
            user_id = g.user_id
            return jsonify({'user': user_id})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        
        if not auth_header:
            return jsonify({
                'error': 'No authorization header',
                'message': 'Authorization header is required'
            }), 401
        
        try:
            # Extract token from "Bearer <token>"
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return jsonify({
                    'error': 'Invalid authorization header',
                    'message': 'Format must be: Bearer <token>'
                }), 401
            
            token = parts[1]
            
            # Decode JWT token using Supabase JWT secret
            decoded = jwt.decode(
                token,
                os.getenv('SUPABASE_JWT_SECRET'),
                algorithms=['HS256'],
                audience='authenticated'
            )
            
            # Extract user information from token
            g.user_id = decoded.get('sub')  # Subject = User ID
            g.user_email = decoded.get('email')
            
            # Get role from user_metadata or app_metadata
            user_metadata = decoded.get('user_metadata', {})
            app_metadata = decoded.get('app_metadata', {})
            g.user_role = user_metadata.get('role') or app_metadata.get('role') or 'user'
            
            # Log for debugging
            print(f"[AUTH] User authenticated: {g.user_id} ({g.user_email}) - Role: {g.user_role}")
            
            return f(*args, **kwargs)
            
        except jwt.ExpiredSignatureError:
            return jsonify({
                'error': 'Token expired',
                'message': 'Your session has expired. Please log in again.'
            }), 401
        except jwt.InvalidTokenError as e:
            return jsonify({
                'error': 'Invalid token',
                'message': f'Token validation failed: {str(e)}'
            }), 401
        except Exception as e:
            print(f"[AUTH ERROR] {str(e)}")
            return jsonify({
                'error': 'Authentication failed',
                'message': 'Unable to authenticate request'
            }), 401
    
    return decorated_function


def require_role(required_role):
    """
    Decorator that checks if user has required role.
    Must be used AFTER @require_auth decorator.
    
    Role hierarchy: user < analyst < admin
    
    Usage:
        @app.route('/admin-only')
        @require_auth
        @require_role('admin')
        def admin_route():
            return jsonify({'message': 'Admin access granted'})
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = getattr(g, 'user_role', 'user')
            
            # Define role hierarchy
            role_hierarchy = {
                'user': 0,
                'analyst': 1,
                'admin': 2
            }
            
            user_level = role_hierarchy.get(user_role, 0)
            required_level = role_hierarchy.get(required_role, 0)
            
            if user_level < required_level:
                return jsonify({
                    'error': 'Insufficient permissions',
                    'message': f'This action requires {required_role} role or higher',
                    'your_role': user_role
                }), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def get_current_user_id():
    """
    Helper function to get current user ID from Flask g object.
    Returns None if not authenticated.
    """
    return getattr(g, 'user_id', None)


def get_current_user_email():
    """
    Helper function to get current user email from Flask g object.
    Returns None if not authenticated.
    """
    return getattr(g, 'user_email', None)


def get_current_user_role():
    """
    Helper function to get current user role from Flask g object.
    Returns 'user' as default if not authenticated.
    """
    return getattr(g, 'user_role', 'user')
